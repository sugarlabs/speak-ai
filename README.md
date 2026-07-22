What is this?
=============

Speak is a voice synthesis activity for the Sugar desktop.

Speak shows a face that will talk what is typed, within reason.

How to use?
===========

Speak is part of the Sugar desktop and is often included.  Please refer to;

* [How to Get Sugar on sugarlabs.org](https://sugarlabs.org/),
* [How to use Sugar](https://help.sugarlabs.org/),
* [Download Speak using Browse](https://v4.activities.sugarlabs.org/), search for `Speak`, then download, and;
* [How to use Speak](https://help.sugarlabs.org/en/speak.html).

How to upgrade?
===============

On Sugar desktop systems;
* use [My Settings](https://help.sugarlabs.org/en/my_settings.html), [Software Update](https://help.sugarlabs.org/en/my_settings.html#software-update), or;
* use Browse to open [v4.activities.sugarlabs.org](https://v4.activities.sugarlabs.org/), search for `Speak`, then download.

How to integrate?
=================

Speak depends on Python, [Sugar Toolkit for GTK+ 3](https://github.com/sugarlabs/sugar-toolkit-gtk3), GStreamer 1, GTK+ 3, and gst-plugins-espeak.

Speak is started by [Sugar](https://github.com/sugarlabs/sugar).

Speak is [packaged by Fedora](https://src.fedoraproject.org/rpms/sugar-speak).  On Fedora systems;

```
dnf install sugar-speak
```

Speak is not packaged by Debian and Ubuntu distributions.  On Debian
and Ubuntu systems dependencies include `gstreamer1.0-espeak`,
`gir1.2-gstreamer-1.0`, and `gir1.2-gst-plugins-base-1.0`.

Branch master
=============

The `master` branch targets an environment with latest stable release
of [Sugar](https://github.com/sugarlabs/sugar), with dependencies on
latest stable release of Fedora and Debian distributions.

Branch not-gstreamer1
=====================

The `not-gstreamer1` branch is a backport of features and bug fixes
from the `master` branch for ongoing maintenance of the activity on
Fedora 18 systems which don't have well-functioning GStreamer 1
packages.

Note: This activity is designed to run inside the Sugar desktop environment. Running it      outside Sugar will cause errors. 

> See below for platform-specific guidance.

### Cross-Platform Setup Notes
=====================

### Running Outside Sugar Environment

Running:

    python activity.py

outside the Sugar desktop/runtime may throw:

    ModuleNotFoundError: dbus

This is expected because `activity.py` depends on the Sugar runtime and system-level dbus integration.

### Windows / Non-Sugar Platform Notes

On Windows (without Sugar installed), the full activity cannot run outside the Sugar runtime.

However, core modules like TTS and LLM components can still be tested independently without the full Sugar environment.

### Testing Core AI Modules Independently

Examples:

    python LLM.py
    python voice.py

This allows partial development and testing without requiring the full Sugar desktop environment.

### Testing the Full Sugar Activity

To run the complete activity, use one of the following:

- Sugar Desktop (Linux)
- Sugar Live Build

### Platform-Specific Notes

- Linux: Recommended environment with native Sugar support.
- Windows: Use WSL2 for partial compatibility.
- macOS: Use a Linux VM for full activity testing.
