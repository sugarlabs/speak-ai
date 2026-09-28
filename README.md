What is this?
=============

SpeakAI is a voice synthesis activity for the Sugar desktop.

SpeakAI shows a face that will talk what is typed, within reason.

It uses [kokoro](https://github.com/hexgrad/kokoro) for TTS, and supports
multiple personas and voices.

Install kokoro with;

```
pip install kokoro
```


How to use?
===========

SpeakAI isn't part of the Sugar desktop and isn't often included.  Please refer to;

* [How to Get Sugar on sugarlabs.org](https://sugarlabs.org/),
* [How to use Sugar](https://help.sugarlabs.org/),
* [Download SpeakAI using Browse](https://v4.activities.sugarlabs.org/), search for `SpeakAI`, then download, and;

How to upgrade?
===============

On Sugar desktop systems;
* use Browse to open [v4.activities.sugarlabs.org](https://v4.activities.sugarlabs.org/), search for `SpeakAI`, then download.

How to integrate?
=================

SpeakAI depends on Python, [Sugar Toolkit for GTK+ 3](https://github.com/sugarlabs/sugar-toolkit-gtk3), GStreamer 1, GTK+ 3, and gst-plugins-espeak.

SpeakAI is started by [Sugar](https://github.com/sugarlabs/sugar).


SpeakAI is not packaged by Debian and Ubuntu distributions.  On Debian
and Ubuntu systems dependencies include `gstreamer1.0-espeak`,
`gir1.2-gstreamer-1.0`, and `gir1.2-gst-plugins-base-1.0`.

Branch master
=============

The `master` branch targets an environment with latest stable release
of [Sugar](https://github.com/sugarlabs/sugar), with dependencies on
latest stable release of Fedora and Debian distributions.
