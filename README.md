# Speak AI

Speak AI is a voice synthesis activity for the Sugar desktop.

It shows a face that will speak what is typed, within reason.

## How to use

Speak AI is part of the Sugar desktop and is often included. Please refer to:

* [How to Get Sugar on sugarlabs.org](https://sugarlabs.org/)
* [How to use Sugar](https://help.sugarlabs.org/)
* [Download Speak AI using Browse](https://v4.activities.sugarlabs.org/) — search for `Speak AI` and download
* [How to use Speak AI](https://help.sugarlabs.org/en/speak.html)

## How to upgrade

On Sugar desktop systems:

* Use [My Settings](https://help.sugarlabs.org/en/my_settings.html), [Software Update](https://help.sugarlabs.org/en/my_settings.html#software-update), or
* Use Browse to open [v4.activities.sugarlabs.org](https://v4.activities.sugarlabs.org/), search for `Speak AI`, and download

## How to integrate

Speak AI depends on:

* Python
* [Sugar Toolkit for GTK+ 3](https://github.com/sugarlabs/sugar-toolkit-gtk3)
* GStreamer 1
* GTK+ 3
* gst-plugins-espeak

Speak AI is started by [Sugar](https://github.com/sugarlabs/sugar).

On Fedora systems:

On Debian/Ubuntu systems, dependencies include:

* `gstreamer1.0-espeak`
* `gir1.2-gstreamer-1.0`
* `gir1.2-gst-plugins-base-1.0`

## Branches

**master**: Targets latest stable Sugar with Fedora and Debian latest releases.  
**not-gstreamer1**: Backport for older Fedora 18 systems without stable GStreamer 1.