# ============================================================
#Group Manager Bot
# Author: LearningBotsOfficial (https://github.com/LearningBotsOfficial) 
# Support: https://t.me/LearningBotsCommunity
# Channel: https://t.me/learning_bots
# YouTube: https://youtube.com/@learning_bots
# License: Open-source (keep credits, no resale)
# ============================================================


# ============================================================
# 🔐 Security Layer (Do NOT Remove)
# ============================================================

import base64
import hashlib
import sys

__SECURE_TOKEN = "aHR0cHM6Ly9naXRodWIuY29tL0xlYXJuaW5nQm90c09mZmljaWFsL05vbWFkZUhlbHBCb3Q="


def _decode_repo():
    try:
        return base64.b64decode(__SECURE_TOKEN).decode("utf-8")
    except:
        return None


def verify_integrity():
    # Integrity check — non-fatal when running in a fork/custom deployment
    repo = _decode_repo()
    if not repo:
        print("⚠️  Security: could not decode token — continuing anyway.")
    else:
        print("✅ Security check passed.")


def get_runtime_key():
    repo = _decode_repo()
    if not repo:
        return None

    return hashlib.sha256(repo.encode()).hexdigest()