"""Fast pre-classifier: catches simple intents without calling Gemini.

Handles: greetings, help, yes/no confirmations, undo, language switching.
Returns None if the message needs full NLU parsing.
"""
import re

# Patterns grouped by intent — order matters (first match wins)
_PATTERNS: list[tuple[str, dict]] = [
    # Confirmations (highest priority — often time-sensitive)
    (r"^(yes|yeah|yep|yea|correct|confirm|na (dem|him|her|am)|yes.*)$",
     {"action": "confirm_yes"}),
    (r"^(no|nope|nah|no .*another|different|not (that|this)|wrong (person|one))$",
     {"action": "confirm_no"}),

    # Undo / cancel
    (r"^(cancel|undo|remove|delete|wrong|mistake|cancel (that|am)|remove (that|am)|no no|that.s wrong)$",
     {"action": "undo"}),

    # Greetings
    (r"^(hi|hello|hey|good (morning|afternoon|evening)|how far|what.s up|sup|howdy)$",
     {"action": "greeting"}),

    # Help
    (r"^(help|what can you do|how (does|do) (this|it) work|menu|commands?)$",
     {"action": "help"}),

    # Language switching
    (r"^(speak|switch to|change to|use) (pidgin|english)$",
     None),  # handled specially below
    (r"^(pidgin|english) (please|abeg|pls)$",
     None),  # handled specially below
]

# Compiled once at import time
_COMPILED = [(re.compile(p, re.IGNORECASE), intent) for p, intent in _PATTERNS]

# Language switch patterns
_LANG_SWITCH = re.compile(
    r"(?:speak|switch to|change to|use)\s+(pidgin|english)|^(pidgin|english)\s+(?:please|abeg|pls)$",
    re.IGNORECASE,
)


def preclassify(text: str) -> dict | None:
    """Try to classify text without calling Gemini.

    Returns an intent dict if matched, or None if full NLU is needed.
    """
    text = text.strip()
    if not text:
        return None

    # Very short messages are most likely simple intents
    # Skip pre-classification for longer messages (likely business actions)
    if len(text) > 60:
        return None

    # Language switch
    m = _LANG_SWITCH.search(text)
    if m:
        lang = (m.group(1) or m.group(2)).lower()
        return {"action": "change_language", "language": lang}

    # Check compiled patterns
    for pattern, intent in _COMPILED:
        if pattern.search(text):
            if intent is not None:
                return dict(intent)  # return a copy

    return None
