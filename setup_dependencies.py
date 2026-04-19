"""
First-run dependency installer for Speak-AI.

On first launch, prompts user for consent and installs
kokoro-onnx and onnxruntime via pip, respecting system
architecture (x86, ARM, etc).

As described by @mebinthattil in PR #9 discussion:
"We can have pip install the dependencies after the
activity is launched for the first time (after user consent).
Pip would take care of which binary to pull based on the
client's system architecture."

Author: Uday Kumar Reddy
GSoC 2026 - Speak-AI Multilingual Support
"""

import subprocess
import sys
import logging
import os

logger = logging.getLogger(__name__)

# Dependencies needed for ONNX-based TTS
REQUIRED_PACKAGES = [
    'kokoro-onnx',
    'onnxruntime',
    'soundfile',
]

CONSENT_FLAG_FILE = 'deps_installed'


def is_first_run(activity_root: str) -> bool:
    """Check if this is the first time the activity runs."""
    flag = os.path.join(activity_root, CONSENT_FLAG_FILE)
    return not os.path.exists(flag)


def mark_installed(activity_root: str) -> None:
    """Mark dependencies as installed so we skip next time."""
    flag = os.path.join(activity_root, CONSENT_FLAG_FILE)
    with open(flag, 'w') as f:
        f.write('installed')


def check_dependencies() -> bool:
    """
    Check if all required packages are importable.

    Returns:
        True if all dependencies are available, False otherwise
    """
    try:
        import kokoro_onnx  # noqa: F401
        import onnxruntime  # noqa: F401
        import soundfile    # noqa: F401
        return True
    except ImportError:
        return False


def install_dependencies() -> bool:
    """
    Install required packages via pip.

    Uses sys.executable to ensure pip installs into the
    same Python environment the activity is running in.
    Pip automatically selects the correct binary for the
    system architecture (x86_64, aarch64, armv7l etc).

    Returns:
        True if installation succeeded, False otherwise
    """
    logger.info("Installing Speak-AI dependencies via pip...")
    try:
        result = subprocess.run(
            [
                sys.executable, '-m', 'pip', 'install',
                '--quiet',
                '--no-warn-script-location',
            ] + REQUIRED_PACKAGES,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        if result.returncode == 0:
            logger.info("Dependencies installed successfully.")
            return True
        else:
            logger.error(
                f"pip install failed: {result.stderr}"
            )
            return False

    except subprocess.TimeoutExpired:
        logger.error("Dependency installation timed out.")
        return False
    except Exception as e:
        logger.error(f"Installation error: {e}")
        return False


def setup_on_first_run(activity_root: str) -> bool:
    """
    Run the first-time setup if dependencies are missing.

    This should be called early in activity startup.
    Returns True if dependencies are ready, False if setup failed.

    Args:
        activity_root: Path from sugar3.activity.activity.get_activity_root()

    Returns:
        True if all dependencies available and ready
    """
    # Already installed — skip
    if check_dependencies():
        return True

    # Not first run but still missing — try reinstall
    if not is_first_run(activity_root):
        logger.warning(
            "Dependencies missing despite previous install. "
            "Attempting reinstall."
        )

    logger.info(
        "First run detected. Installing required packages: "
        f"{', '.join(REQUIRED_PACKAGES)}"
    )

    success = install_dependencies()

    if success:
        mark_installed(activity_root)
        logger.info("First-run setup complete.")
    else:
        logger.error(
            "First-run setup failed. Activity may not work correctly."
        )

    return success