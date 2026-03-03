"""Google Forms API wrapper."""

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class FormsClient:
    """Client for Google Forms API operations."""

    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self.service = build("forms", "v1", credentials=credentials)

    def create(self, title: str, description: str = "") -> dict:
        """Create a new Google Form.

        The Forms API ignores description in the create request, so we use a
        two-step flow: create the form, then set description via batchUpdate.

        Args:
            title: Form title
            description: Optional form description

        Returns:
            Dict with formId, title, responderUri, and editUri
        """
        try:
            form_data: dict = {"info": {"title": title}}
            result = self.service.forms().create(body=form_data).execute()
            form_id = result.get("formId", "")

            if description:
                self.service.forms().batchUpdate(
                    formId=form_id,
                    body={
                        "requests": [
                            {
                                "updateFormInfo": {
                                    "info": {"description": description},
                                    "updateMask": "description",
                                }
                            }
                        ]
                    },
                ).execute()

            return {
                "formId": form_id,
                "title": result.get("info", {}).get("title", title),
                "description": description,
                "responderUri": result.get("responderUri", ""),
                "editUri": f"https://docs.google.com/forms/d/{form_id}/edit",
            }
        except HttpError as error:
            raise RuntimeError(f"Forms API error: {error}")

    def read(self, form_id: str) -> dict:
        """Read form structure and questions.

        Args:
            form_id: The form ID

        Returns:
            Dict with formId, title, description, items, and publish state
        """
        try:
            form = self.service.forms().get(formId=form_id).execute()
            result: dict = {
                "formId": form_id,
                "title": form.get("info", {}).get("title", ""),
                "description": form.get("info", {}).get("description", ""),
                "responderUri": form.get("responderUri", ""),
                "items": self._simplify_items(form.get("items", [])),
            }
            publish_state = (
                form.get("publishSettings", {}).get("publishState")
            )
            if publish_state is not None:
                result["isPublished"] = publish_state.get(
                    "isPublished", False
                )
                result["isAcceptingResponses"] = publish_state.get(
                    "isAcceptingResponses", False
                )
            return result
        except HttpError as error:
            raise RuntimeError(f"Forms API error: {error}")

    def responses(self, form_id: str, limit: int = 100, page_token: str | None = None) -> dict:
        """List form responses.

        Args:
            form_id: The form ID
            limit: Maximum number of responses to return
            page_token: Token for fetching next page of results

        Returns:
            Dict with formId, responseCount, responses list, and optional nextPageToken
        """
        try:
            kwargs: dict = {"formId": form_id, "pageSize": limit}
            if page_token:
                kwargs["pageToken"] = page_token
            result = self.service.forms().responses().list(**kwargs).execute()
            raw_responses = result.get("responses", [])
            response: dict = {
                "formId": form_id,
                "responseCount": len(raw_responses),
                "responses": raw_responses,
            }
            if result.get("nextPageToken"):
                response["nextPageToken"] = result["nextPageToken"]
            return response
        except HttpError as error:
            raise RuntimeError(f"Forms API error: {error}")

    def add_question(
        self,
        form_id: str,
        title: str,
        question_type: str = "text",
        required: bool = False,
        choices: list[str] | None = None,
        goto: dict[str, str] | None = None,
        index: int | None = None,
    ) -> dict:
        """Add a question to a form.

        Args:
            form_id: The form ID
            title: Question text
            question_type: One of "text", "paragraph", "choice", "checkbox",
                          "dropdown", "scale"
            required: Whether the question is required
            choices: Options for choice/checkbox/dropdown types
            goto: Map of choice text → section ID or action for branching.
                  Actions: SUBMIT_FORM, NEXT_SECTION, RESTART_FORM.
                  Only valid for choice/dropdown types (not checkbox).
            index: Position to insert at (appends if None)

        Returns:
            Dict with formId and status

        Raises:
            ValueError: If choice/checkbox/dropdown has no choices, or goto
                       used with checkbox type.
        """
        if question_type in ("choice", "checkbox", "dropdown") and not choices:
            raise ValueError("Choice questions require at least one option")

        if goto and question_type == "checkbox":
            raise ValueError("Branching (--goto) is not supported for checkbox questions")

        _GOTO_ACTIONS = {"SUBMIT_FORM", "NEXT_SECTION", "RESTART_FORM"}

        try:
            question: dict = {"required": required}

            if question_type in ("text", "paragraph"):
                question["textQuestion"] = {"paragraph": question_type == "paragraph"}
            elif question_type in ("choice", "checkbox", "dropdown"):
                type_map = {
                    "choice": "RADIO",
                    "checkbox": "CHECKBOX",
                    "dropdown": "DROP_DOWN",
                }
                options = []
                for c in (choices or []):
                    opt: dict = {"value": c}
                    if goto and c in goto:
                        target = goto[c]
                        if target in _GOTO_ACTIONS:
                            opt["goToAction"] = target
                        else:
                            opt["goToSectionId"] = target
                    options.append(opt)
                question["choiceQuestion"] = {
                    "type": type_map[question_type],
                    "options": options,
                }
            elif question_type == "scale":
                question["scaleQuestion"] = {"low": 1, "high": 5}

            if index is None:
                form = self.service.forms().get(formId=form_id).execute()
                index = len(form.get("items", []))

            request: dict = {
                "createItem": {
                    "item": {
                        "title": title,
                        "questionItem": {"question": question},
                    },
                    "location": {"index": index},
                }
            }

            self.service.forms().batchUpdate(
                formId=form_id,
                body={"requests": [request]},
            ).execute()

            return {"formId": form_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Forms API error: {error}")

    def add_section(
        self,
        form_id: str,
        title: str,
        description: str = "",
        section_id: str | None = None,
        index: int | None = None,
    ) -> dict:
        """Add a section break to a form.

        Args:
            form_id: The form ID
            title: Section title
            description: Optional section description
            section_id: Custom item ID for branching references
            index: Position to insert at (appends if None)

        Returns:
            Dict with formId and status
        """
        try:
            item: dict = {
                "title": title,
                "description": description,
                "pageBreakItem": {},
            }
            if section_id is not None:
                item["itemId"] = section_id

            if index is None:
                form = self.service.forms().get(formId=form_id).execute()
                index = len(form.get("items", []))

            request: dict = {
                "createItem": {
                    "item": item,
                    "location": {"index": index},
                }
            }

            self.service.forms().batchUpdate(
                formId=form_id,
                body={"requests": [request]},
            ).execute()

            return {"formId": form_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Forms API error: {error}")

    def _find_item_index(self, form_id: str, item_id: str) -> tuple[int, dict]:
        """Read form and find an item by its ID.

        Args:
            form_id: The form ID
            item_id: The item ID to find

        Returns:
            Tuple of (positional index, item data)

        Raises:
            ValueError: If the item ID is not found in the form
        """
        form = self.service.forms().get(formId=form_id).execute()
        for i, item in enumerate(form.get("items", [])):
            if item.get("itemId") == item_id:
                return i, item
        raise ValueError(f"Item '{item_id}' not found in form '{form_id}'")

    def update_form(
        self, form_id: str, title: str | None = None, description: str | None = None
    ) -> dict:
        """Update form metadata (title and/or description).

        Args:
            form_id: The form ID
            title: New form title (None to leave unchanged)
            description: New form description (None to leave unchanged)

        Returns:
            Dict with formId and status

        Raises:
            ValueError: If neither title nor description is provided
        """
        if title is None and description is None:
            raise ValueError("At least one of --title or --description is required")

        try:
            info: dict = {}
            mask_fields = []
            if title is not None:
                info["title"] = title
                mask_fields.append("title")
            if description is not None:
                info["description"] = description
                mask_fields.append("description")

            self.service.forms().batchUpdate(
                formId=form_id,
                body={
                    "requests": [
                        {
                            "updateFormInfo": {
                                "info": info,
                                "updateMask": ",".join(mask_fields),
                            }
                        }
                    ]
                },
            ).execute()

            return {"formId": form_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Forms API error: {error}")

    def publish(
        self, form_id: str, accepting_responses: bool = True
    ) -> dict:
        """Publish a form so it can accept responses.

        Args:
            form_id: The form ID
            accepting_responses: Whether the form accepts new submissions

        Returns:
            Dict with formId and status
        """
        try:
            self.service.forms().setPublishSettings(
                formId=form_id,
                body={
                    "publishSettings": {
                        "publishState": {
                            "isPublished": True,
                            "isAcceptingResponses": accepting_responses,
                        }
                    }
                },
            ).execute()
            return {"formId": form_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Forms API error: {error}")

    def unpublish(self, form_id: str) -> dict:
        """Unpublish a form (stops accepting responses automatically).

        Args:
            form_id: The form ID

        Returns:
            Dict with formId and status
        """
        try:
            self.service.forms().setPublishSettings(
                formId=form_id,
                body={
                    "publishSettings": {
                        "publishState": {
                            "isPublished": False,
                        }
                    }
                },
            ).execute()
            return {"formId": form_id, "status": "ok"}
        except HttpError as error:
            raise RuntimeError(f"Forms API error: {error}")

    def update_item(
        self,
        form_id: str,
        item_id: str,
        title: str | None = None,
        description: str | None = None,
        required: bool | None = None,
        choices: list[str] | None = None,
        goto: dict[str, str] | None = None,
    ) -> dict:
        """Update an existing item (question or section) in a form.

        Args:
            form_id: The form ID
            item_id: The item ID to update
            title: New item title (None to leave unchanged)
            description: New item description (None to leave unchanged)
            required: New required flag for questions (None to leave unchanged)
            choices: Replacement options for choice/checkbox/dropdown (None to leave unchanged)
            goto: Map of choice text -> section ID or action for branching
                  (None to leave unchanged)

        Returns:
            Dict with formId and status
        """
        _GOTO_ACTIONS = {"SUBMIT_FORM", "NEXT_SECTION", "RESTART_FORM"}

        try:
            index, existing_item = self._find_item_index(form_id, item_id)

            item: dict = {}
            mask_fields: list[str] = []

            if title is not None:
                item["title"] = title
                mask_fields.append("title")
            if description is not None:
                item["description"] = description
                mask_fields.append("description")

            # Handle question-specific fields
            if "questionItem" in existing_item:
                question_updates: dict = {}
                existing_q = existing_item["questionItem"]["question"]

                if required is not None:
                    question_updates["required"] = required
                    mask_fields.append("questionItem.question.required")

                if choices is not None:
                    # Determine question type from existing item
                    if "choiceQuestion" in existing_q:
                        existing_type = existing_q["choiceQuestion"].get("type", "RADIO")
                        options = []
                        for c in choices:
                            opt: dict = {"value": c}
                            if goto and c in goto:
                                target = goto[c]
                                if target in _GOTO_ACTIONS:
                                    opt["goToAction"] = target
                                else:
                                    opt["goToSectionId"] = target
                            options.append(opt)
                        question_updates["choiceQuestion"] = {
                            "type": existing_type,
                            "options": options,
                        }
                        mask_fields.append("questionItem.question.choiceQuestion")
                    else:
                        raise ValueError(
                            "--choices can only be used on choice/checkbox/dropdown questions"
                        )
                elif goto is not None:
                    raise ValueError("--goto requires --choices (options are replaced as a set)")

                if question_updates:
                    item["questionItem"] = {"question": question_updates}

            update_request: dict = {
                "updateItem": {
                    "item": {"itemId": item_id, **item},
                    "location": {"index": index},
                    "updateMask": ",".join(mask_fields),
                }
            }

            self.service.forms().batchUpdate(
                formId=form_id,
                body={"requests": [update_request]},
            ).execute()

            return {"formId": form_id, "status": "ok"}
        except ValueError:
            raise
        except HttpError as error:
            raise RuntimeError(f"Forms API error: {error}")

    def delete_item(self, form_id: str, item_id: str) -> dict:
        """Delete an item (question or section) from a form.

        Args:
            form_id: The form ID
            item_id: The item ID to delete

        Returns:
            Dict with formId and status
        """
        try:
            index, _ = self._find_item_index(form_id, item_id)

            self.service.forms().batchUpdate(
                formId=form_id,
                body={
                    "requests": [
                        {"deleteItem": {"location": {"index": index}}}
                    ]
                },
            ).execute()

            return {"formId": form_id, "status": "ok"}
        except ValueError:
            raise
        except HttpError as error:
            raise RuntimeError(f"Forms API error: {error}")

    def _simplify_items(self, items: list[dict]) -> list[dict]:
        """Simplify form items for readable output."""
        simplified = []
        for item in items:
            entry: dict = {"title": item.get("title", "")}
            if item.get("itemId"):
                entry["itemId"] = item["itemId"]
            if item.get("description"):
                entry["description"] = item["description"]

            if "questionItem" in item:
                q = item["questionItem"]["question"]
                if "textQuestion" in q:
                    entry["type"] = "paragraph" if q["textQuestion"].get("paragraph") else "text"
                elif "choiceQuestion" in q:
                    cq = q["choiceQuestion"]
                    type_map = {
                        "RADIO": "choice",
                        "CHECKBOX": "checkbox",
                        "DROP_DOWN": "dropdown",
                    }
                    entry["type"] = type_map.get(cq.get("type", ""), "choice")
                    options = []
                    for o in cq.get("options", []):
                        opt: dict = {"value": o.get("value", "")}
                        if o.get("goToSectionId"):
                            opt["goToSectionId"] = o["goToSectionId"]
                        if o.get("goToAction"):
                            opt["goToAction"] = o["goToAction"]
                        options.append(opt)
                    # Flatten to simple list if no branching present
                    if any("goToSectionId" in o or "goToAction" in o for o in options):
                        entry["options"] = options
                    else:
                        entry["options"] = [o["value"] for o in options]
                elif "scaleQuestion" in q:
                    sq = q["scaleQuestion"]
                    entry["type"] = "scale"
                    entry["low"] = sq.get("low", 1)
                    entry["high"] = sq.get("high", 5)
                    if sq.get("lowLabel"):
                        entry["lowLabel"] = sq["lowLabel"]
                    if sq.get("highLabel"):
                        entry["highLabel"] = sq["highLabel"]
                entry["required"] = q.get("required", False)
            elif "pageBreakItem" in item:
                entry["type"] = "section"

            simplified.append(entry)
        return simplified
