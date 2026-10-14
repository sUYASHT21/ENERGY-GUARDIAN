# Smart Energy Guardian — Panel Review Speaker Guide

Deck: `SmartEnergyGuardian_PredictX_Pitch_Deck.pptx` (16 slides). The same script is also in each
slide's **speaker notes** in PowerPoint.

**Team:** Suyash Tatiya (24BEE0087) · Arjun Gupta (24BEE0064) · Arya Suman (24BEE0032)
**Faculty Mentor:** Ravichandra Halagatti

| Part | Speaker | Slides | Topic | Time |
|---|---|---|---|---|
| 1 | **Arya** | 1–4 | The pitch: problem, impact, what's new | ~4 min |
| 2 | **Suyash** | 5–8 | How the project works: architecture, decision engine, ML, demo flow | ~5 min |
| 3 | **Arjun** | 9–12, 15–16 | The software we built, project status, hardware plan, roadmap | ~5 min |
| All | everyone | 13–14 | Team and who did what (each person reads their own part) | ~1 min |

---

## The whole project in one minute (everyone should know this)

* **Problem:** lights, fans, projectors and ACs stay ON in empty classrooms, labs and hostels.
  Nobody sees it room by room, so money and electricity are wasted.
* **Idea:** put a small, cheap device (an **ESP32**) in each room. It reads **occupancy** (is anyone
  there?) and **power** (how many watts each appliance uses) every 5 seconds and sends it to our server.
* **Brain:** the server runs a **decision engine** — a list of 20 safety checks — to decide if it is
  real waste. If yes, it tells the ESP32 to switch the appliance **off with a relay**.
  A **machine-learning model (Isolation Forest)** separately watches for **electrical faults**.
* **Screen:** a **React dashboard** shows live power, energy used and wasted, ₹ cost, CO₂, alerts and
  savings.
* **Status:** **software is complete and working** (tested with a simulator and an ESP32 emulator).
  **Hardware is in progress** — parts are chosen and the plan is ready; we will build it and show a
  live demo in the **final review**.

### Simple meaning of the technical words

| Word | Say it like this |
|---|---|
| ESP32 | A small, cheap Wi-Fi microcontroller — the "brain" in each room |
| PIR / mmWave sensor | Detects if people are in the room |
| PZEM-004T / SCT-013 | Measures current, voltage and power of an appliance (CT clamp goes around the wire) |
| Relay | An electrically controlled switch, so the ESP32 can turn an appliance on/off |
| Telemetry | The readings the ESP32 sends to the server every 5 seconds |
| FastAPI | The Python framework our backend server is written in |
| REST API | The "doors" the dashboard and the ESP32 use to talk to the server (we have 57) |
| WebSocket | A live connection so the dashboard updates by itself without refreshing |
| Isolation Forest | An ML algorithm that learns what "normal" looks like and flags readings that are unusual |
| Dry-run mode | The system only *writes down* what it would switch off — nothing is actually switched |
| Simulator / emulator | Software that pretends to be rooms / an ESP32, so we can test without hardware |
| kWh | A "unit" of electricity on the bill |

---

## Part 1 — Arya: The pitch (slides 1–4)

**Slide 1 — Title.**
"Good morning. We are team Jack Schneider from EEE. Our project is **Smart Energy Guardian** — an
AI-based IoT system that finds electricity wasted in empty campus rooms and switches it off safely.
Our mentor is Prof. Ravichandra Halagatti. I'll explain the problem and our idea, Suyash will explain
how it works, and Arjun will show the working software and our status. In short: our **software is
complete and working**, and the **hardware build is in progress** for the final review."

**Slide 2 — Smart Energy Guardian (problem + solution).**
* Problem: appliances keep running in empty rooms; facility teams have no room-level visibility.
* Solution, three steps: **sense** (ESP32 reads occupancy and power every 5 s) → **decide** (safety
  checks + ML) → **act** (relay switches off, dashboard shows alert and savings).
* Point at the tech stack: ESP32 + sensors, Python FastAPI, scikit-learn, React.

**Slide 3 — Why it matters.**
"One classroom with 6 lights, 4 fans and one AC is about 2 kW. If it runs empty only 3 hours a day,
in a year that is about **1,350 units, ₹10,800 and almost 1 tonne of CO₂ — for one room**. For 100
rooms: about **1.35 lakh units and ₹10.8 lakh per year**." Say clearly: *these are our own
illustrative assumptions*, and in our simulated campus about **16%** of energy was used in empty rooms.

**Slide 4 — Innovation.**
Today: manual switching, timers, or simple motion sensors that switch off wrongly and show nothing.
Ours: (1) ML on the electrical signal, (2) several sensors on one cheap ESP32, (3) **every decision is
explained check by check**, (4) closed loop — the relay must confirm, savings are tracked,
(5) already tested with a simulator, so hardware plugs in without changing the software.
Hand over: "Now Suyash will explain how it works inside."

## Part 2 — Suyash: How it works (slides 5–8)

**Slide 5 — Architecture (4 layers).**
1. **Room node:** ESP32 + occupancy sensor + power meter + relay, sends data every 5 s.
2. **Backend (Python FastAPI):** converts power to energy (kWh), calculates waste, cost and CO₂,
   scores every reading with ML, and a monitor loop runs the decision engine every 3 s.
3. **Database:** SQLite on a laptop or PostgreSQL in the cloud.
4. **Dashboard (React):** live updates via WebSocket, login with viewer/operator/admin roles.
Key line: "Our simulator and ESP32 emulator send **exactly the same messages** a real ESP32 will, so
the full software path is already tested."

**Slide 6 — Decision engine (safety first).**
Four stages, an appliance goes OFF only if **all** pass:
1. **Data quality** — fresh reading, sensor OK, device online. If not → do nothing.
2. **Wastage** — appliance ON and room empty for the minimum time (10 min).
3. **Safety policy** — not essential (server, fridge), no manual override, no class now or in the next
   10 min. If not → only a recommendation.
4. **Mode** — recommend / dry-run (default) / auto. The relay must confirm within 20 s.
"Real hardware switching needs 3 keys at once. And **ML never switches anything off by itself** —
it only raises an alert."

**Slide 7 — ML anomaly detection.**
"Isolation Forest learns what normal electrical readings look like; readings that are easy to separate
from the rest are anomalies." It catches over-consumption, spikes, voltage faults, low power factor and
phantom load (power flowing when the relay says OFF — a stuck relay). 5 features, 200 trees, trained
on 16,000 readings, tested on 8,000 unseen readings. Results: **ROC-AUC 0.995, recall 86.7%,
precision 70.1%, 1.1% false alarms**; weakest is voltage fault (59%).
**Be honest:** "This is synthetic data from our own simulator — it proves the pipeline works; real
accuracy will be measured with hardware data."

**Slide 8 — Prototype & demo flow.**
Sensing → Edge node → Intelligence → Action. Stage: **working software demo**; hardware in progress.
Scenarios we can show: empty-room waste, anomaly, sensor failure, offline device, failed/timed-out
command. **127 automated tests pass.** Hand over to Arjun.

## Part 3 — Arjun: The software, status and plan (slides 9–12, 15–16)

**Slide 9 — Live dashboard (real screenshots).**
Left: campus overview — live kW, energy today, **energy wasted in empty rooms** (red), CO₂, and
estimated savings. Right: a room page — the seminar room is empty but lights, fans, projector and AC
are ON; opening the AC shows **every check** with a green tick and the reason. Every screen says if
data is *Simulated*, *Emulated ESP32* or *Hardware*; savings are marked *Estimate*.

**Slide 10 — Automation & history.**
Command log: first **dry-run** ("I would switch these 4 off"), then in **Auto** mode real OFF commands
were sent and **acknowledged** in about 3 seconds. If a relay fails or doesn't reply in 20 s → failed /
timeout + alert. Energy history: blue = used while occupied, orange = wasted while empty. ML page shows
the metrics. "In a live demo these 4 steps take about 2 minutes."

**Slide 11 — Project status.** (most important for this review)
* **Software — completed:** backend, decision engine, ML model, dashboard (12 pages), simulator,
  emulator, Docker/cloud setup; **57 APIs, 127 tests passing**.
* **Hardware — in progress:** components selected, wiring/pin plan done, ESP32 firmware drafted,
  device protocol tested with the emulator. **The physical build has not started yet.**
* **For the final review:** buy parts, build and bench-test one room node, connect it to this same
  dashboard, and show a live relay shutdown with real readings.

**Slide 12 — Hardware plan.**
Parts: ESP32, PIR/mmWave, PZEM-004T + CT clamp, 4-channel relay, 5 V supply, optional temperature
sensor. Safety: the relay's **normally-closed** contact keeps lights/fans **ON** if the ESP32 crashes;
every OFF is confirmed by the power meter; mains wiring under lab supervision. Plan: procure →
assemble & bench-test → connect in dry-run → live demo at final review.
(If Arya leads hardware, she can present this slide instead.)

**Slides 13–14 — Team (everyone).** Each person says their own role and tasks in ~15 s, then thank
the mentor.

**Slide 15 — Roadmap.** Next: build hardware, calibrate on real data, polish for the final review.
If we win: pilot in real campus buildings. Long term: blueprint for smart campuses, hostels and
commercial buildings.

**Slide 16 — Thank you.** "Thank you — we're happy to take questions."

---

## How to talk about the hardware (agree on this wording)

> "Our software is complete and fully tested using a simulator and an ESP32 emulator that use the exact
> same communication protocol as the real device. The hardware design is ready — components, wiring plan
> and firmware draft — but we have not started the physical build yet. We will build one room node and
> show a live demo with real readings in the final review."

Do **not** say the hardware works or that the ML accuracy is real-world accuracy.

## Likely panel questions — short answers

| Question | Who | Answer |
|---|---|---|
| Why is hardware not ready? | Arjun / Arya | We built and tested the full software first so the hardware only has to plug in. Design is ready; the build is planned before the final review. |
| What if someone sits still and PIR thinks the room is empty? | Suyash | Minimum vacancy time (10 min), no switch-off during scheduled classes, manual override, and mmWave sensors detect still people better. Default mode is dry-run. |
| Can it switch off a server or a lab experiment? | Suyash | No. Essential loads are excluded completely; lab machines can be "manual only"; the system then only recommends. |
| What happens if Wi-Fi or the ESP32 fails? | Arya | The relay's normally-closed contact keeps loads ON; the server marks the device offline and stops automation. |
| Is your ML accuracy real? | Suyash | No — it's on synthetic data from our simulator. It proves the pipeline; we'll re-measure on real hardware data. |
| Why Isolation Forest and not Random Forest? | Suyash | Isolation Forest needs no labelled fault data, which we don't have yet. Random Forest is an option once we collect labelled real data. |
| How do you calculate savings? | Arya | Power just before the switch-off × time it stayed off (max 8 h). It's an estimate and labelled as one. Energy itself uses the trapezoidal rule on readings. |
| What is the cost per room? | Arya | Low-cost: one ESP32, one occupancy sensor, power meters and a relay board — check current market prices before quoting a number. |
| Where does it run? | Arjun | Locally with Docker, or free cloud: dashboard on Vercel, backend on Render, database on Supabase PostgreSQL. |
| How did you test it? | Arjun | 105 backend tests, 18 frontend tests and 4 end-to-end browser tests — 127 in total, all passing. |

## Before the review — checklist

* Confirm the **roles on slides 13–14** match what each person actually did (edit if needed).
* Each speaker: read your speaker notes twice; practise hand-overs ("Now Suyash will…").
* Keep the live demo ready (`docker compose up --build` → http://localhost:8080, login `admin` /
  `guardian-demo`); if it fails, slides 9–10 already show the real screens.
