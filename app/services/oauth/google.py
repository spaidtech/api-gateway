from typing import Any
from pydantic import EmailStr, TypeAdapter

class GoogleOAuthProvider:
    name = "google"

    @staticmethod
    def extract_user_data(user_info: dict[str, Any]) -> dict[str, str | None]:
        provider_user_id = user_info.get("sub")
        email = user_info.get("email")

        if not provider_user_id or not email or user_info.get("email_verified") is not True:
            raise ValueError(
                "Google did not provide required verified user information"
            )

        validated_email = TypeAdapter(EmailStr).validate_python(email)

        return {
            "provider": "google",
            "provider_user_id": provider_user_id,
            "email": str(validated_email),
            "first_name": user_info.get("given_name"),
            "last_name": user_info.get("family_name")
        }
