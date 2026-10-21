# SDL Color Lab

[中文版](README.zh-CN.md)

Local colour-matching experiments with a **React frontend**, a **Python/FastAPI backend**, and an **Opentrons OT-2 protocol**. An operator moves files and the plate between the page, the OT-2 App and the plate reader. The page generates recipes, converts measured absorbance spectra to sRGB, and tracks **CIEDE2000 colour error (ΔE₀₀)**.

**Each experiment uses one model for six rounds.** Choose GPT-6 or BO-EI before starting; the model is then fixed. To test the other model, create a separate experiment. For a comparison, use the same target and working stocks in both experiments. Each method submits one candidate per round, with red, green, blue and water totalling **200 µL**. GPT uses **A1–A6**; BO uses **B1–B6**. No dye calibration is needed: neither method receives measured base-dye RGB, Lab or spectra. Reagent names and the target remain available, and each method uses only its own measured history.

GPT directly reasons out its first recipe. BO’s first recipe is reproducible exploration using **seed 0**, without a fitted model; rounds 2–6 fit a GP and use EI, implemented as LogEI, on BO’s own results. This first exploration is included in the six-round budget. **Success means ΔE₀₀ ≤ 1**, including exactly 1; all six rounds are completed even if success is reached early.

## 1. Install and start

### First setup from GitHub

Download or clone the repository and open a terminal in the project root. Install Python 3 and **Node.js 22.12 or later** for the initial frontend build. Build once:

```sh
# macOS
python3 scripts/build_frontend.py
```

```bat
:: Windows
py -3 scripts\build_frontend.py
```

The build uses `frontend/package-lock.json` and creates `frontend/dist/`. The generated folder is ignored by Git, so a fresh GitHub checkout needs this step. Rebuild after changing frontend source. A prepared local copy that already contains `frontend/dist/index.html` can skip this step.

### Start an experiment

1. For GPT, create the root `.env` from [.env.example](.env.example) and fill in the model settings described below. BO-EI does not require these settings.
2. Double-click [start_macos.command](start_macos.command) on macOS or [start_windows.bat](start_windows.bat) on Windows. The launcher installs locked Python dependencies on the first run; internet access is required. It uses the backend's single environment, including **Opentrons 9.0.0** and **NumPy 1.26.4**, with Python **3.10–3.12** support.
3. Keep the launch window open. The browser opens at **http://127.0.0.1:8501/**. Node.js is not needed for subsequent operation of the built page.

To use another port, run `python3 scripts/launch.py --port 8502` on macOS, or `py -3 scripts\launch.py --port 8502` on Windows. Use the exact address opened by the launcher.

The page opens in **English**. Use **EN / ZH** at the top right to switch languages without losing the current upload or experiment. Refreshing returns to English. The experiment selector prefixes each record with its selected method: **BO-EI** or the configured GPT model ID.

**Server operation.** A cloud deployment uses the same workflow. Set `COLOR_LAB_PUBLIC_ORIGIN` to the exact public origin (for example, `https://your-server-address`, without a trailing slash) and keep the backend behind an HTTPS reverse proxy that preserves the request Host and Origin. Keep `.env` on the server for the backend only. The cloud page downloads each recipe CSV to the operator's computer instead of opening a server folder; experiment progress and original uploads are stored on the server.

## 2. Prepare a live experiment

**Model configuration.** For GPT, copy [.env.example](.env.example) to `.env` in the same folder. Fill in `OPENAI_API_KEY`, the actual available `OPENAI_MODEL`, and `OPENAI_BASE_URL` if using a compatible endpoint. Restart the service after editing. Finder shows hidden files with **Command + Shift + .**. The page checks the connection when GPT is first selected. BO can run without an API key or GPT connection. The GPT model ID and endpoint are fixed when the experiment is created; create a new experiment if changing them.

The initial and feedback prompts are in **English**, independently of the page language. New requests ask for reasoning in English; previously archived requests and replies retain their original text.

**Prepare stocks.** Prepare red, green and blue working stocks and water, with the brand/batch and dilution recorded for the organiser. Do not prepare or upload base-dye calibration wells. Keep the plate type, **200 µL** volume, reader settings and background processing consistent for all candidate measurements.

Set the target colour and start directly. Upload a spectrum only after a candidate has been mixed and measured. Uploaded absorbance is converted as provided; the page does not subtract a blank.

**Spectrum format.** Use one UTF-8 CSV per spectrum, with two columns:

```csv
Wavelength(nm),OD Value
380,0.1728566485933389
381,0.17839566290272532
```

This illustrates the structure only. The full upload must cover **380–780 nm**, with increasing, unique wavelengths, gaps no larger than **10 nm**, and valid non-negative absorbance values. A 1 nm scan matches the supplied examples. The alternative header `wavelength_nm,absorbance` is also accepted. A complete example is [base_Blue.csv](backend/src/sdl_color_lab/resources/data/base_Blue.csv); red and green examples are in the same folder.

The current page accepts this CSV format. If the organiser provides a different export, obtain an actual sample for adaptation before the experiment.

**Start.** Choose **GPT-6** or **BO-EI**, set the target RGB (default **143, 150, 106**), then click **Start [method] · 6 rounds**. The page automatically assigns an experiment ID and candidate wells. The model and initial settings are fixed for this experiment. Restoring an experiment retains its current model, original calibration, recipes and history.

## 3. Set up the OT-2 once

Keep the project on the same local computer used to operate the OT-2. Complete the first setup above, then start the page with the root macOS/Windows launcher. Install and open the **[Opentrons OT-2 App](https://opentrons.com/ot-app)** separately; installing the Python package does not install this desktop application or connect the robot. Keep the page's launch window open while using the App.

The **Opentrons OT-2 App** controls the robot; the web page exchanges CSV files. Connect that computer to the OT-2 by Ethernet or an already configured local network, and select the robot under **Devices**.

Click **Download script · Once** on the setup or experiment page to save `SDL_CSV_protocol.py`, then import it through **Protocols → Import**. The same file is included at [opentrons/SDL_CSV_protocol.py](opentrons/SDL_CSV_protocol.py). The robot software must support **Protocol API 2.28**. Check the physical layout against the App analysis and complete pipette/labware offset checks.

This one Python protocol defines the pipettes, source positions, transfers and mixing, and is reused for all rounds. The CSV supplies the current well and component volumes; the script reads its contents through the App's **Recipe CSV** parameter. A changed protocol must be re-imported and analysed. The web launcher starts the page only; the operator chooses the round's CSV and starts each robot run in the OT-2 App.

| Item | Required setup |
|---|---|
| Pipettes | Left: `p20_single_gen2`; right: `p300_single_gen2`, both single-channel |
| Slot 10 | `opentrons_96_tiprack_300ul` |
| Slot 11 | `opentrons_96_tiprack_20ul` |
| Slot 7 | `corning_96_wellplate_360ul_flat` |
| Slot 8 | `opentrons_10_tuberack_falcon_4x50ml_6x15ml_conical` |
| Modules | None required; the P300 pipette performs mixing |
| Source rack positions | A3 water; A4 red; B3 green; B4 blue, using the four 50 mL tube positions |

For a two-model comparison using two separate experiments, start with the first **60 positions unused in each tip rack**, and keep the racks in place across the twelve executions. The protocol reserves five positions per pipette per execution.

**Before liquid handling:** the current code assumes **45 mL initially per source tube** and aspirates **40 mm above the tube bottom**. Both P20 and P300 use this bottom-referenced position for all water/red/green/blue source transfers, including pre-wetting. These inherited values have not been verified on the physical setup. The robot operator must confirm liquid levels, tip reach and labware offsets, and adjust/reanalyse the protocol if necessary. Final destination-well mixing is separate: **100 µL once**, **2 mm above the well bottom**; do not apply the source's 40 mm setting to this mix. Verify that mixing gives a uniform sample in the actual plate. Re-import and analyse the protocol after changing the deck layout or liquid-handling settings. Command-line simulation does not replace the on-site App analysis and liquid trial.

## 4. Repeat this cycle for every candidate

1. **Generate:** check the method, round and well shown on the page, then click **Generate recipe**.
2. **Transfer:** the recipe CSV is saved automatically inside the project. Click **Open CSV folder** and, in the OT-2 App, choose this round's file for **Recipe CSV**. Reanalyse; verify the well, execution number, four volumes and deck, then start the run. Download/import the Python script once, then reuse it.
3. **Measure:** wait for the App to report completion. The protocol adds water, red, green and blue, then mixes. Move the plate to the reader with its orientation preserved and measure the current well.
4. **Upload:** upload that well’s two-column spectrum CSV on the current round. Check the RGB/colour and ΔE₀₀, then click **Confirm colour & finish round**.
5. **Continue:** generate the next candidate for this experiment’s fixed model. Success means **ΔE₀₀ ≤ 1**; complete all six rounds even if this is reached early. To test another model, select **New experiment** from the experiment selector and choose it before starting. Each experiment keeps its own recipes and measurements.

Each experiment has one readable folder under **`runtime/experiments/<model_ID>/`**. Its **`opentrons/`** folder contains the recipe CSVs, and **`results.csv`** lists each round's well, recipe, RGB and colour error. The page shows the exact CSV folder; **Open CSV folder** opens it in the file manager. Clicking the filename optionally downloads another copy. The hidden **`.state/`** folder keeps original spectra, model logs and recovery records; **`runtime/.cache/`** is managed by the program. An explicitly configured external experiments directory uses the same structure. Keep the whole experiment folder together.

The CSV does **not** need to be next to the Python protocol: the App supplies the selected file through the protocol's CSV parameter. Each round, start a new setup for the same protocol and select the new CSV. Filenames include the model/method, round and well: e.g. `gpt-6-astra_R01_A1.csv` (using the experiment's actual GPT model ID) or `BO-EI_R01_B1.csv`. The script reads the CSV contents rather than relying on its filename; keep those contents unchanged. The recipe CSV goes to the OT-2 App; the measured spectrum CSV goes back to the web page.

A single-spectrum CSV contains no well ID. The operator must ensure that the uploaded file belongs to the displayed well. The page binds it to that round. For CSVs without a measurement timestamp, the record uses the **feedback submission time**, not a claimed instrument acquisition time.

| Method | Method round | Reserved tip-allocation ID | Candidate wells |
|---|---|---|---|
| GPT-6 | 1–6 | 1–6 | A1–A6 |
| BO-EI | 1–6 | 7–12 | B1–B6 |

Use the current round's CSV saved by the page. Its nine-column contract is shown below; this is a format example, not a recipe to execute:

```csv
iteration,execution_index,recipe_id,replicate,well,water_ul,red_ul,green_ul,blue_ul
1,7,bo-1-example,1,B1,80,40,30,50
```

Each file contains one candidate, `replicate=1`, and non-negative integer volumes summing to 200. `execution_index` reserves a unique tip block: GPT uses 1–6, BO uses 7–12, regardless of execution order. **BO round 1 uses ID 7 even when it is the first experiment run.** Downloading does not mean dispensing has occurred. A repeat download keeps the same well and tip allocation.

## 5. Resume, troubleshoot and finish

| Situation | Operator action |
|---|---|
| Browser/service closed | Run the launcher again and restore the experiment with **Select experiment**. Keep the project’s `runtime/` data. |
| Model connection or generation fails | Check the local configuration/network and retry the current round. No substitute model is selected automatically. |
| Spectrum rejected | Check the two headers, complete wavelength range and numeric values. Upload the correct current-well CSV. |
| Feedback was interrupted | Restore the same experiment and upload the same CSV again. The archived result/time is reused. Conflicting data cannot overwrite a completed round. |
| Robot run partially completed | Stop and ask the robot operator to inspect added volumes, used wells and tips before planning recovery. **Do not rerun the same CSV blindly.** |

The chart shows measured colour error by round; **lower ΔE₀₀ is better**. **Round results** below the chart lists each recorded candidate's model, round, well, recipe volumes, RGB colour and ΔE₀₀. The model is fixed for this experiment and its budget is **six rounds**. Use the single **Download experiment records** link in the experiment panel to save the ZIP, during or after the run. It includes recipes, measurements, original files and model logs. Elapsed time includes manual handoffs and measurement waits.

The organiser prepares the stocks, connects and operates the devices, transfers the plate and returns the spectra. The page operator generates recipes, hands over the CSVs, checks sample/file identity and records feedback.

## 6. Repository layout

```text
frontend/       React page, interaction, charts and API client
backend/        FastAPI, GPT/BO algorithms, spectra conversion and experiment state
opentrons/      Standalone SDL_CSV_protocol.py for the OT-2 App
scripts/        Local launch and frontend build tools
runtime/        Local experiment folders and program-managed cache (Git-ignored)
.env.example    Configuration template; copy to .env for local settings
README.md       English operator guide
README.zh-CN.md  Chinese operator guide
```

Git includes the source code, both dependency lockfiles, configuration template and operator guides. `.gitignore` excludes local `.env` files, experiment data in `runtime/`, local diagrams in `visuals/`, installed dependencies and generated builds. Keep `.env.example` in the repository; keep the actual `.env` and experiment folders on the operating computer. The guides are self-contained and do not depend on `visuals/`.
