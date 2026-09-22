# Pilot price check

Checked 2026-09-22 using Context7's OpenAI API documentation index.
Source: https://developers.openai.com/api/docs/models/gpt-4.1-mini

The returned GPT-4.1 mini pricing section lists USD 0.40 per million input tokens,
USD 0.10 per million cached input tokens and USD 1.60 per million output tokens.
Reservations and accounting upper estimates use no cache discount.

The installed openai==2.11.0 source, types/chat/completion_create_params.py,
documents service_tier=default as standard pricing. Omitting it means auto, which
can inherit project settings. The pilot transport therefore adds service_tier=default
to the native request without changing messages, tools or report schema, and stops
if the response does not confirm that tier.

This checks documented pricing, not account-specific billing or model availability.
No provider model request was used to check prices. Preserve reported token usage
and conservative reservations separately from any future billing receipt.
