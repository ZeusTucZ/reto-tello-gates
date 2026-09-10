# Plan de validación progresiva

No continuar al siguiente test si falla el anterior. Mantener zona despejada,
protecciones, observador y salida manual accesible. Guardar por ensayo: fecha,
operador, batería inicial/final, configuración, iluminación, video, CSV, resultado
y observación de fallos. No declarar éxito físico basándose sólo en estado DONE.

## Estado de evidencia

- Validación estática: imports y compilación se comprueban sin efectos de hardware.
- Validación de software: pruebas de geometría, signos, deadband, saturación,
  EMA, estabilidad, pérdida, estados, batería y watchdog con mocks/sintéticos.
- Validación por video: prueba de integración sobre video **sintético** MJPG que
  recorre SEARCH, ALIGN, APPROACH, CROSS y DONE. No demuestra control en lazo físico.
- Validación con video real: pendiente de agregar muestras etiquetadas.
- Validación física con Tello: **pendiente; no se ejecutó vuelo ni cruce real**.

Comandos reproducibles (desde raíz, `.venv` activado):

```powershell
python -m unittest discover -s tests -v
python -m compileall -q main.py gate_detector.py controller.py config.py video_source.py hsv_calibration.py tests samples/generate_sample.py
python samples/generate_sample.py
python main.py --video samples/synthetic_gate.avi --dry-run --headless --log-csv samples/run.csv
```

## Test 1 — Conexión + batería

- [ ] **Objetivo:** confirmar comunicación sin movimiento. Conectar Windows al Wi-Fi
  Tello y ejecutar `python main.py --dry-run --stage hover`.
- **Éxito:** consola informa conexión y batería válida; ninguna orden de despegue.
- **Observar:** IP/red, porcentaje y actualización de telemetría; batería mínima configurada.
- **Si falla:** comprobar encendido, Wi-Fi, firewall y que otra app no ocupe conexión.
  No habilitar vuelo. Cerrar con q/ESC.

## Test 2 — Video stream sin vuelo

- [ ] **Objetivo:** recibir imagen continua con el mismo comando del Test 1.
- **Éxito:** mover un objeto frente a la cámara cambia la imagen sin congelamientos;
  los colores originales se ven correctos y el dron permanece en el piso.
- **Observar:** FPS, pausas, orientación, color, mensajes de video ausente.
- **Si falla:** revisar stream, Wi-Fi, interferencias y dependencias PyAV/DJITelloPy;
  no desactivar el watchdog como solución.

## Test 3 — HSV y detección con Tello en el piso

- [ ] **Objetivo:** `python hsv_calibration.py`, copiar valores y ejecutar
  `python main.py --dry-run` con gate a la vista.
- **Éxito:** máscara conserva marco/hueco y bbox correcto; escenas negativas no
  producen detecciones estables. Medir y registrar errores, no asumir precisión.
- **Observar:** HSV, morfología, área, aspecto, hueco, score y contadores.
- **Si falla:** seguir `CALIBRATION.md`, mejorar luz/fondo y repetir con negativos.

## Test 4 — Centroide y error X/Y

- [ ] **Objetivo:** mover gate en imagen sin mover el Tello.
- **Éxito:** centroide sigue el marco; derecha produce X positivo, izquierda
  negativo, arriba Y positivo, abajo negativo, centrado aproximadamente cero.
- **Observar:** cruz de imagen, centro del gate, línea de error, bbox y deadband.
- **Si falla:** revisar geometría, cámara/BGR y fórmulas antes de tocar Kp.

## Test 5 — DRY RUN mostrando comandos sin vuelo

- [ ] **Objetivo:** `python main.py --dry-run --log-csv samples/dry_run.csv`.
- **Éxito:** LR/UD tienen signo correcto, se saturan, son cero en deadband; FB
  sólo aparece con estabilidad/alineación. Perder gate detiene FB. Motores quietos.
- **Observar:** RC, estados, `detected/aligned/lost`, ratio y watchdog.
- **Si falla:** regresar a detección o controlador; probar tests unitarios y video local.

## Test 6 — Takeoff + hover sin autonomía

- [ ] **Objetivo:** después de aprobar Test 5, poner `DRY_RUN=False`, ejecutar
  `python main.py --stage hover` y pulsar t con video válido.
- **Éxito:** despega, mantiene RC cero y q/ESC inicia aterrizaje controlado.
- **Observar:** deriva, batería, altura inicial del SDK, latencia de parada,
  `TAKEOFF_SETTLE_SECONDS`, `MAX_FLIGHT_SECONDS`.
- **Si falla:** aterrizar, revisar superficie/luz/posición y comunicaciones. No
  avanzar a autonomía. El SDK controla la altura de despegue, no este controlador.

## Test 7 — Control únicamente horizontal

- [ ] **Objetivo:** `python main.py --stage horizontal`, gate visible, t.
- **Éxito:** un pequeño error X produce corrección física correcta y decreciente;
  FB/UD/yaw permanecen cero.
- **Observar:** `KP_X`, `MAX_LR_SPEED`, `DEADBAND_X`, `EMA_ALPHA`, sobrepaso y deriva.
- **Si falla:** q/ESC; revisar signo, ruido/latencia; ajustar Kp sin subir varios límites a la vez.

## Test 8 — Control horizontal + vertical

- [ ] **Objetivo:** `python main.py --stage align`, t; introducir errores pequeños X/Y.
- **Éxito:** ambos errores disminuyen con correcciones del signo esperado; FB/yaw cero.
- **Observar:** `KP_X/Y`, `MAX_LR_SPEED`, `MAX_UD_SPEED`, deadbands y acoplamiento físico.
- **Si falla:** aterrizar; repetir un eje a la vez, reducir oscilaciones y revisar perspectiva.

## Test 9 — ALIGN completo

- [ ] **Objetivo:** repetir `--stage align` desde varios offsets controlados.
- **Éxito:** alcanza y mantiene ambos errores dentro de deadband durante al menos
  `ALIGNED_FRAMES` observaciones, sin avance. Pérdida causa RC cero y eventual aborto.
- **Observar:** contadores, tiempo de establecimiento y falsos saltos de objetivo.
- **Si falla:** recalibrar estabilidad, detector o control y repetir Test 8.

## Test 10 — APPROACH con velocidad muy baja

- [ ] **Objetivo:** `python main.py --stage approach` con `APPROACH_SPEED` calibrada baja.
- **Éxito:** avanza sólo tras ALIGN estable, conserva corrección; al perder gate o
  desalinearse detiene FB. No ejecuta CROSS en esta etapa.
- **Observar:** distancia real de frenado, histéresis, contadores y batería.
- **Si falla:** q/ESC, reducir avance, revisar latencia y volver a ALIGN.

## Test 11 — Detección de proximidad

- [ ] **Objetivo:** medir ratio a distancias conocidas en piso, luego observar
  `--stage approach` detener avance al alcanzar `CLOSE_WIDTH_RATIO`.
- **Éxito:** threshold ocurre a distancia útil y repetible con marco todavía visible
  y margen físico suficiente. Registrar medidas; no inferir metros sólo del ratio.
- **Observar:** ratio, distancia, inclinación/perspectiva, recorte de bordes y alineación.
- **Si falla:** ajustar threshold y repetir Test 10; jamás forzar CROSS con detección inestable.

## Test 12 — CROSS

- [ ] **Objetivo:** calibrar desplazamiento en espacio abierto primero; después
  `python main.py --stage full` con gate y trayectoria despejados.
- **Éxito:** sólo entra a CROSS por cercanía/alineación estables; tolera pérdida del
  contorno durante el paso, termina RC en cero y aterriza. Un observador confirma cruce.
- **Observar:** `CROSS_SPEED`, `CROSS_DURATION`, distancia recorrida, deriva LR/UD,
  tiempo de frenado y espacio posterior.
- **Si falla:** parada manual, volver a Test 11; ajustar velocidad/duración con
  medidas físicas. No interpretar DONE como confirmación del paso.

## Test final — Secuencia completa

- [ ] **Objetivo:** demostrar `detecta → alinea → aproxima → cruza → se detiene/aterriza`.
- **Éxito:** video externo y CSV concuerdan, se atraviesa sin contacto, se detiene
  y aterriza en zona prevista; registrar cantidad de intentos y fallos reales.
- **Observar:** todas las transiciones, errores, batería, condiciones, trayectoria y seguridad.
- **Si falla:** documentar el estado/causa y volver al test aislado correspondiente.
  Mantener el resultado como pendiente/fallido hasta contar con evidencia física.

## Pruebas de fallos antes de CROSS

En DRY RUN ensaya pérdida del gate, frames ausentes, desconexión, batería simulada
baja, q/ESC/Ctrl+C y cierre de ventana. Los tests automatizados cubren varios de
estos casos con mocks. Verifica la parada en hover físico sólo en un entorno donde
se pueda recuperar el dron. No provoques una desconexión intencional en vuelo para
demostrar un aterrizaje que UDP no puede garantizar.

## Resultado de la ejecución sin hardware

En esta implementación se ejecutaron **31 tests, todos aprobados**, y compilación
con `compileall` sin errores. Imports de los seis módulos verificados sin conectar
un Tello. Entorno observado: Python 3.13.14, OpenCV 5.0.0, NumPy 2.5.3 y DJITelloPy 2.5.0.

La ejecución CLI del video sintético terminó con `state=DONE`, 212 frames
procesados y `dry_run=True`. El CSV `samples/run.csv` conserva los comandos
calculados y todas las transiciones de navegación. Los fallos de batería, captura,
telemetría, watchdog y parada se ensayaron con hardware simulado.

No se midieron precisión, latencia extremo a extremo, distancias ni vuelos reales.
La visualización se verificó por renderizado en memoria; revisión interactiva de
las ventanas/trackbars y captura con webcam/Tello permanecen pendientes.