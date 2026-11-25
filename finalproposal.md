## Project Title

SPEAK-AI MULTILINGUAL SUPPORT

---

**Working On:**
Improving Robustness and Flexibility of the Text-to-Speech Pipeline in Speak Activity

---

## Basic Details

**Full Name:** Kavya Kumari
**Email:** Kavyalohani24@gmail.com
**GitHub Username:** Kavyalohani 
**GitHub Profile:** https://github.com/Kavyalohani  

**First Language:** English (comfortable with Hindi for communication)
**Location & Timezone:** India (IST, UTC +5:30)

**Previous Open Source Work:**

* Active contributor to Speak Activity (Sugar Labs)

**Sugar Labs Contributions:**

**Forked Repository:** https://github.com/Kavyalohani/speak-ai-my-version- 

* PR #70: https://github.com/sugarlabs/speak-ai/pull/70
→  Added Hindi Text-to-Speech support using gTTS, enabling  multilingual capability

* PR #77: https://github.com/sugarlabs/speak-ai/pull/77
→ Introduced fallback handling between Kokoro and gTTS for improved reliability

* PR #80: https://github.com/sugarlabs/speak-ai/pull/80
 → Improved error handling and stability to prevent pipeline crashes during failures

---

## Introduction

Hello, I am a sophomore in B.Tech CSE at IILM University, Greater Noida, with a strong interest in open-source development, systems design, and building reliable software for real-world users.

The Speak Activity is an important educational tool in Sugar Labs, and its usability heavily depends on the reliability of its speech system.

I have been actively contributing to the Speak Activity, focusing on improving the Text-to-Speech (TTS) pipeline.

My contributions include:

* Adding Hindi TTS support using gTTS (PR #70)
* Introducing fallback handling between Kokoro and gTTS (PR #77)
* Improving error handling and preventing pipeline crashes (PR #80)

Through these contributions, I have:

* Analyzed backend-specific failure patterns
* Identified architectural limitations in fallback handling
* Understood latency and reliability trade-offs between offline and API-based TTS

This proposal is a **Direct continuation of my prior contributions.**, aiming to evolve the current pipeline into a **robust, modular, and decision-driven system**, especially optimized for students in low-connectivity environments.

---

## What are you making?

The current TTS pipeline lacks structured decision-making and relies primarily on reactive, failure-based fallback between backends. This leads to:

* Increased latency
* Unnecessary backend calls
* Reduced reliability in constrained environments

This project proposes a structured and modular TTS pipeline with improved backend selection logic, enabling more predictable and context-aware backend selection.

Key improvements:

* **Backend Readiness Checks**
  Avoid invoking uninitialized or unavailable backends

* **Condition-Aware Backend Selection**
  Selection based on:

  * Language
  * Network availability
  * Backend capability

* **Deterministic Fallback Strategy**
  Precomputed backend execution order instead of failure-triggered switching

* **Modular Backend Abstraction**
  Decoupled backend interfaces for extensibility

* **Robust Error Handling & Fault Isolation**
  Prevent a single backend failure from breaking the pipeline

---

## Proposed Design

### Core Architecture Upgrade

Current:
Text → Kokoro → gTTS → espeak

Proposed:
Text → TTS Orchestrator → Decision Engine → Backend Execution → Output

The orchestrator will integrate with the existing **GStreamer-based audio pipeline**, ensuring compatibility with current playback mechanisms while improving backend selection logic.

---

### Backend Abstraction Layer

```python id="final1"
class TTSBackend:
    def is_available(self) -> bool:
        pass

    def supports_language(self, lang: str) -> bool:
        pass

    def synthesize(self, text: str):
        pass
```

This enables:

* Loose coupling
* Easy integration of new TTS engines
* Simplified testing and debugging

---

### Decision Flow

1. Detect runtime context:

   * Language
   * Network state
   * Backend readiness

2. Generate ordered backend list

3. Execute sequentially with controlled fallback

---

### Intelligent Backend Routing

| Scenario         | Priority Order         |
| ---------------- | ---------------------- |
| Offline          | espeak → Kokoro        |
| Hindi (online)   | gTTS → Kokoro → espeak |
| English (online) | Kokoro → gTTS → espeak |

---

### Fallback Strategy

Instead of:
Failure → Retry → Switch

We use:
Plan → Execute → Controlled fallback

Additionally, **timeout-based fallback mechanisms** will be introduced to prevent blocking due to slow API responses (e.g., gTTS latency).

---

### Logging & Observability

Structured logging will be added:

* Backend selection decisions
* Failure causes
* Fallback transitions

This improves debugging, monitoring, and long-term maintainability.

---

### Extensibility Consideration

* New TTS engines can be integrated easily
* Backend logic remains independent
* Core orchestrator remains stable

---

### Pipeline Overview

Text → Context Detection → Decision Engine → Backend Execution → Output

---

## Expected Outcomes (Quantitative Impact)

* Significant reduction in TTS failures through structured fallback
* Reduced latency caused by unnecessary backend retries
* Improved reliability in low-connectivity environments
* Better system stability and fewer pipeline crashes
---

## How will it impact Sugar Labs?

### For Students

* Reliable speech output even in low connectivity
* Improved multilingual accessibility
* Reduced delays and failures

### For Developers

* Cleaner, modular architecture
* Easier debugging with structured logs
* Scalable system for future TTS engines

### System-Level Impact

* More predictable performance
* Improved robustness
* Better maintainability

---

## Technologies

* Python
* GStreamer (Gst, GLib)
* Kokoro TTS
* Google Text-to-Speech (gTTS)
* espeak
* Git & GitHub

---

## Timeline

### Community Bonding Period

* Deep dive into architecture
* Finalize orchestrator design with mentors
* Identify integration points

---

### Week 1–2

* Refactor fallback logic
* Implement backend abstraction layer
* Add readiness checks

---

### Week 3–4

* Implement decision engine
* Introduce deterministic fallback

---

### Week 5 (Evaluation 1)

* Functional orchestrator
* Initial testing

---

### Week 6–7

* Language-aware routing
* Network-aware backend selection

---

### Week 8–9

* Configuration system
* Logging system

---

### Week 10 (Evaluation 2)

* Stability improvements
* Documentation

---

### Week 11–12

* Extensive testing
* Performance optimization
* Final refinements

---

### Buffer Time

* Edge cases
* Mentor feedback

---

## Testing Strategy

* Unit tests for each backend (with mocking)
* Integration testing for full pipeline
* Fault injection testing:

  * Simulated network failures
  * Backend crashes
  * Timeout scenarios
* Real-world testing:

  * Low bandwidth environments
  * Multilingual inputs

---

## Time Commitment

I will dedicate approximately **30–35 hours per week** consistently.

---

## Progress Reporting

* Regular GitHub commits and PR updates
* Weekly updates on Matrix / mailing list
* Continuous mentor interaction
* Iterative improvements based on feedback

---

## Understanding of Mentorship

From my PR interactions, I understand mentors prioritize:

* Stability and reliability
* Proper fallback handling
* Maintainable architecture

Their feedback emphasized:

* Avoiding crashes
* Ensuring smooth backend transitions
* Maintaining compatibility

This proposal directly aligns with these expectations.

---

## Why Me

My contributions show clear progression:

* PR #70 → Feature addition (Hindi TTS)
* PR #77 → Backend fallback logic
* PR #80 → Stability improvements

This demonstrates my ability to:

* Understand system-level issues
* Identify architectural gaps
* Improve the system iteratively

In addition, I bring:

* **Strong problem-solving skills**, especially in debugging and handling real-world edge cases  
* **Good understanding of Python and system-level workflows**, including backend integration and error handling  
* **Active communication and collaboration**, as reflected in my interactions on pull requests and community channels  
* **Ability to take feedback and iterate quickly**, improving my contributions based on mentor suggestions  

> Since I have already worked on this pipeline, I can start contributing from day one without onboarding delay.

I am also committed to consistent contribution throughout the program and beyond, ensuring that the work remains maintainable and useful for the community.

This proposal is a **natural evolution of my proven work**, combined with a strong commitment to learning and contributing effectively.

---

## Risk Management

* Backend instability → Multi-level fallback
* API latency (gTTS) → Timeout-based fallback
* Network dependency → Offline-first routing
* Integration complexity → Modular architecture
* Timeline risks → Buffer + phased milestones

---

## Future Scope

* Integration of additional TTS engines
* GUI-based backend selection
* Voice customization
* Offline neural TTS

---

## Post GSoC Plans

* Continue contributing to Speak Activity
* Maintain and improve TTS pipeline
* Help onboard new contributors

---

## Final Statement

This project transforms the Speak Activity from a:

**basic fallback-based pipeline → intelligent, reliable orchestration system**

It ensures:

* Consistent speech output
* Better accessibility for students
* Scalable and maintainable architecture

This is a **system-level improvement focused on real-world reliability**, which is essential for educational environments.

---
