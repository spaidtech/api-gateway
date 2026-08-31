from typing import Any
from pydantic import EmailStr, TypeAdapter


class GithubOAuthProvider:
    name = "github"

    @staticmethod
    def extract_user_data(user_info: dict[str, Any], email: str) -> dict[str, str | None]:
        provider_user_id = user_info.get("id")

        if provider_user_id is None:
            raise ValueError(
                "GitHub did not provide a user ID"
            )

        name = user_info.get("name")

        first_name = None
        last_name = None

        if name:
            name_parts = name.split(maxsplit=1)

            first_name = name_parts[0]

            if len(name_parts) > 1:
                last_name = name_parts[1]


        validated_email = TypeAdapter(EmailStr).validate_python(email)

        return {
            "provider": "github",
            "provider_user_id": str(provider_user_id),
            "email": str(validated_email),
            "first_name": first_name,
            "last_name": last_name
        }