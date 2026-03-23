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

Multilingual Kokoro Support
===========================

Recent improvements include:

* language-family-aware Kokoro pipeline routing based on selected voice;
* script-aware automatic voice selection for text input (Latin, Devanagari,
  Arabic, Chinese Han, and Japanese Kana/Kanji cues), and;
* short phrase audio caching for faster repeated playback.

To preview script detection and automatic voice routing logic:

```
python tools/multilingual_eval.py
```

With custom phrase set:

```
python tools/multilingual_eval.py --phrases-file my_phrases.json
```

The JSON file may be either:

* a list of phrases, or;
* an object like `{"phrases": ["..."]}`.

Multilingual Community Evaluation
=================================

Dataset for multilingual routing checks:

* `tests/data/multilingual_phrases.json`

Run dataset validation:

```
python tools/validate_multilingual_routing.py
```

Community pronunciation template:

* `tests/data/pronunciation_scorecard_template.csv`

Aggregate reviewer scores:

```
python tools/pronunciation_scorecard.py --input tests/data/pronunciation_scorecard_template.csv --output pronunciation_summary.csv
```

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
