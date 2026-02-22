# Speak Activity 🎤

Speak is a voice synthesis activity for the Sugar desktop environment.

It displays an animated face that speaks the text entered by the user, providing an interactive and educational text-to-speech experience.

---

## 🧠 Overview

Speak is designed for use within the Sugar learning platform and is commonly included in Sugar distributions.
It helps children and learners explore speech synthesis in a fun and accessible way.

---

## 🚀 How to Use

Speak is part of the Sugar desktop environment.
Refer to the following resources:

* Get Sugar: https://sugarlabs.org/
* Sugar Help: https://help.sugarlabs.org/
* Download Speak via activities portal: https://v4.activities.sugarlabs.org/
* Usage Guide: https://help.sugarlabs.org/en/speak.html

---

## ⬆️ How to Upgrade

On Sugar desktop systems:

* Use **My Settings → Software Update**, or
* Open https://v4.activities.sugarlabs.org/ in Browse

  * Search for **Speak**
  * Download and install

---

## 🔧 Integration & Dependencies

Speak depends on the following technologies:

* Python
* Sugar Toolkit for GTK+ 3
  https://github.com/sugarlabs/sugar-toolkit-gtk3
* GStreamer 1
* GTK+ 3
* gst-plugins-espeak

Speak is launched and managed by the Sugar environment.

Sugar source: https://github.com/sugarlabs/sugar

---

## 📦 Installation (Fedora)

Speak is packaged for Fedora systems.

Install using:

```bash
dnf install sugar-speak
```

---

## 🐧 Debian / Ubuntu Notes

Speak is not officially packaged for Debian and Ubuntu.
Required dependencies include:

* gstreamer1.0-espeak
* gir1.2-gstreamer-1.0
* gir1.2-gst-plugins-base-1.0

Manual setup may be required.

---

## 🌿 Branch Information

### master

Targets the latest stable Sugar release and modern Fedora/Debian environments.

---

### not-gstreamer1

A legacy branch that backports fixes from `master`
for older systems (e.g., Fedora 18) without stable GStreamer 1 support.

---

## 🤝 Contributing

We welcome contributions from developers and beginners!

Ways to contribute:

* Improve documentation
* Fix bugs
* Modernize dependencies
* Improve accessibility

Steps:

1. Fork the repository
2. Create a feature branch
3. Make changes
4. Submit a Pull Request

---

## 🌍 About Sugar Labs

This project is maintained by the Sugar Labs community,
which builds open-source educational software for children worldwide.

Learn more: https://sugarlabs.org/

---

## 📜 License

Refer to the LICENSE file in this repository.
