# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A first-class lever ("palanca de primer género") physics simulator: a FastAPI/WebSocket backend running a real-time second-order dynamics simulation, streamed to a vanilla-JS canvas frontend. All source, identifiers, and comments are in **Spanish** — match that convention in any new code, comments, or commit-adjacent text within this repo.

## Commands

Run all commands from the repo root. A `.venv` already exists (Python 3.14) with dependencies installed.

```powershell
# Activate the venv (PowerShell)
.venv\Scripts\Activate.ps1

# Run the dev server (http://127.0.0.1:8000)
python -m backend.api.servidor

# Run the full test suite
pytest

# Run a single test file / test
pytest tests/test_dinamica.py
pytest tests/test_simulador.py::test_nombre_de_la_prueba -v

# Install/update deps
pip install -r requirements-dev.txt   # dev (includes runtime deps + pytest + httpx)
pip install -r requirements.txt       # runtime only
```

There is no separate frontend build step — `frontend/` is served as static files directly by FastAPI (`StaticFiles` mount on `/`) and imported as native ES modules by the browser.

## Architecture

The backend is a strict layered pipeline; each layer only talks to the one below it, and physics/formulas are never duplicated across layers:

```
backend/dominio/       — pure physics & domain rules, no I/O, no framework
  modelos.py             frozen dataclasses: ParametrosPalanca (user input),
                          ResultadosEstaticos, ResultadosDinamicos, EstadoSimulacion
  estatica.py             statics: weight, equilibrium force, mechanical advantage,
                          fulcrum reaction. Defines GeneroPalanca (ABC) — only
                          PrimerGenero (first-class lever) is implemented; adding a
                          second/third-class lever means adding another GeneroPalanca
                          subclass, not touching existing code (Open/Closed).
  dinamica.py             second-order dynamics built on top of estatica.py's torque:
                          I·θ'' + c·θ' + k·θ = τ. ModeloDinamico precomputes I and τ
                          once per parameter set so the integrator can call
                          aceleracion_angular() cheaply every substep.
  validadores.py          the ONLY place that trusts client input; converts raw
                          dicts to ParametrosPalanca, checking ranges against
                          configuracion.RANGOS_PARAMETROS (single source of truth).
  excepciones.py          PalancaError hierarchy: ParametroInvalidoError (bad input),
                          SimulacionInestableError (NaN/inf from integration),
                          MensajeMalformadoError (bad WebSocket message).

backend/simulacion/    — turns the dynamics model into a stepped-through-time sim
  integradores.py         Integrador (ABC) contract: paso() validates dt and checks
                          the result is finite; subclasses only implement _avanzar().
                          IntegradorRungeKutta4 (primary, 4th order) and
                          IntegradorEulerSemiimplicito (simple alternative) both
                          satisfy the same contract — the integrator is swappable
                          and knows nothing about the physics (it's handed an
                          acceleration function).
  simulador.py            Simulador owns the live EstadoSimulacion (θ, ω, t),
                          re-derives subpasos-per-frame from the model's fastest
                          mode whenever parameters change (stiff models need a
                          smaller integration step to stay stable with fixed-step
                          RK4), and applies the ±30° mechanical stop
                          (aplicar_tope_mecanico) — an inelastic collision that
                          zeroes outward velocity. One Simulador per connected
                          client; NOT thread-safe.

backend/api/           — protocol translation and network glue
  esquemas.py             WebSocket message protocol: interpretar_mensaje() turns
                          raw JSON into typed MensajeParametros/MensajePerturbar/
                          MensajeReiniciar; serializar_*() turns domain dataclasses
                          back into JSON-safe dicts. Adding a new message type means
                          adding one function + one registry entry (both the
                          _INTERPRETES map here and Sesion._manejadores), never
                          editing the dispatch logic itself.
  sesion.py               Sesion binds one Simulador to the message protocol for
                          one client: procesar_mensaje() dispatches by message
                          type, never raises PalancaError (turns it into an
                          "error" message instead — the connection stays alive),
                          and reinitializes the sim if integration goes unstable.
  servidor.py             FastAPI app: GET /api/configuracion (ranges/gravities for
                          the browser to build its controls), WS /ws (one Sesion
                          per connection, running a receptor task and an emisor
                          task concurrently — first one to finish/disconnect
                          cancels the other), and a static-file mount for
                          frontend/ registered LAST so it doesn't shadow the API
                          routes. crear_aplicacion() takes fabrica_sesion as a
                          parameter so tests can inject a custom Sesion/Simulador.

backend/configuracion.py — single source of truth for every physical constant,
  control range (RangoParametro: min/max/step/label/initial value), gravity table,
  and timing constant (frame rate, substeps, ws message size limit). Angles here
  are in DEGREES for readability; everything below dominio/ converts to radians.
  The frontend never hardcodes ranges — it fetches them from GET /api/configuracion.

frontend/js/            — vanilla ES modules, no build/bundler, no framework
  configuracion.js        frontend-only constants (WS URL derivation, reconnect
                          backoff, chart window) — control ranges are NOT
                          duplicated here, they come from the backend.
  red/clienteWebSocket.js WebSocket client with exponential-backoff reconnect.
  ui/controles.js         reads GET /api/configuracion to build sliders, sends
                          "parametros"/"perturbar"/"reiniciar" messages.
  ui/panelResultados.js   renders "resultados"/"estado"/"error" messages.
  render/renderizadorPalanca.js  canvas drawing of the lever itself.
  render/graficaAngulo.js  rolling time-series chart of angle vs. time.
  main.js                 composition root: wires modules together and drives the
                          requestAnimationFrame draw loop. No physics, no direct
                          DOM manipulation, no validation — purely orchestration.

## Key invariants worth knowing before changing code

- **Sign convention**: positive net torque → effort side goes down, load goes up
  (θ positive). This convention is defined once in `estatica.py` and reused
  by `dinamica.py` — do not re-derive or duplicate the sign logic.
- **Angle units**: degrees in `configuracion.py` (human-facing), radians
  everywhere in `dominio/` and below. `EstadoSimulacion.angulo_grados` is the
  only conversion point back to degrees for display.
- **Validation happens once**: `validadores.py` is the sole gatekeeper between
  untrusted client input and domain dataclasses. Never re-check ranges elsewhere.
- **The mechanical stop (±30°) lives in `simulador.py`, not `dinamica.py`**:
  it's a constraint on motion, not part of the differential equation.
- **`RANGOS_PARAMETROS` keys must match `ParametrosPalanca` field names** —
  `validar_parametros()` iterates the config dict and constructs the dataclass
  from it directly.
