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

### Model Setup (Kokoro-ONNX)

This activity uses the lightweight Kokoro-ONNX backend for high-quality, multilingual text-to-speech. Because the model weights are large binary files (~200MB combined), they are not bundled directly in this repository.

**Automated Download:**
You do not need to download the models manually. Upon launching the activity for the first time, the backend will automatically download the required ONNX model (`kokoro-v1.0.fp16.onnx`) and the voice definitions (`voices-v1.0.bin`) from the official release repositories. 

**Storage Location:**
To adhere to Sugar OS sandboxing guidelines, these files are saved directly to your local writable activity root directory rather than the source code folder. You can find them here:
`~/.sugar/default/org.sugarlabs.SpeakActivity/data/models/`

*(Note: The initial download may take a few minutes depending on your internet connection. Subsequent launches will detect the cached models and boot instantly.)*