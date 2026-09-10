# Fase 2 — navegación visual de un DJI Tello

Implementación Python de cámara → HSV/contornos → centroide → error normalizado →
control P → estados → `send_rc_control()`. Objetivo: alinear, aproximarse y cruzar
un gate físico de aproximadamente 1 × 1 m. No utiliza ROS, Ubuntu, PX4, Gazebo ni YOLO.

**DRY_RUN = True por defecto. Todos los valores iniciales requieren calibración.**
El software no ha sido validado en vuelo. Un CROSS terminado significa que terminó
un temporizador, no que un sensor haya confirmado que el dron cruzó.

## Requisitos e instalación (PowerShell)

Python 3.10 o posterior, OpenCV con GUI (`opencv-python`, no `headless`) y DJITelloPy.
La versión de Python utilizada en las pruebas queda en `docs/VALIDATION.md`.
Desde la raíz de este proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Si `.venv` ya existe, omite su creación. Usar su ejecutable directamente evita
confundir `python3`, `pip` y otras instalaciones. Activación opcional:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Los ejemplos siguientes usan `python` suponiendo el entorno activado. También
puedes sustituirlo por `.\.venv\Scripts\python.exe` en todos los comandos.

## Conexión y calibración HSV, sin vuelo

1. Enciende el Tello y conecta Windows a su Wi-Fi `TELLO-XXXXXX`.
2. Es normal que esa red no tenga Internet. Instala dependencias antes de conectarte.
3. Cierra otras aplicaciones que estén usando el stream/comandos del Tello.
4. Permite a Python el acceso a esa red si Windows Firewall lo solicita.
5. Coloca el gate frente a la cámara y ejecuta:

```powershell
python hsv_calibration.py
```

Ajusta H/S/V min/max hasta que la máscara conserve el marco y elimine el fondo.
Se muestran original, máscara y resultado filtrado. La consola imprime valores al
cambiarlos; `p` los imprime otra vez. Copia `HSV_MIN` y `HSV_MAX` a `config.py`.
El ejemplo inicial es verde y exige un marco con hueco interior. Para rojo que
cruce el límite H=179/0 se requiere ampliar el detector a dos intervalos: esta
versión usa uno, o puedes elegir otro color de gate.

Alternativas sin Tello:

```powershell
python hsv_calibration.py --webcam 0
python hsv_calibration.py --video samples/gate_test.mp4
```

El archivo se repite y espacio pausa la imagen local para ajustar sliders.
La calibración nunca despega ni envía RC.

## DRY RUN: pipeline completo sin movimiento

Con Tello conectado a Wi-Fi, en el piso:

```powershell
python main.py --dry-run
```

Con video real previamente grabado o webcam:

```powershell
python main.py --video samples/gate_test.mp4 --dry-run
python main.py --webcam 0 --dry-run
```

Sin hardware ni archivo propio, genera la muestra sintética:

```powershell
python samples/generate_sample.py
python main.py --video samples/synthetic_gate.avi --dry-run
python main.py --video samples/synthetic_gate.avi --dry-run --headless --log-csv samples/run.csv
```

`--video` y `--webcam` **siempre fuerzan DRY RUN**, incluso con `DRY_RUN=False`.
No construyen un Tello. El video usa tiempo de contenido (`frame / FPS`); headless
lo procesa rápido sin cambiar la duración simulada de CROSS. Una grabación es
reproducción abierta: los comandos calculados no cambian las imágenes futuras.
`--max-frames 100` limita la ejecución. `--log-csv` registra estado, errores y RC.

La ventana muestra bbox, centros, deadband, línea de error, estado, errores,
lr/fb/ud/yaw, ratio, puntuación heurística, FPS de procesamiento y batería.
La máscara se activa con `SHOW_MASK`. En DRY RUN los comandos son **calculados**,
no enviados, y DONE no llama a `land()`.

## Habilitar vuelo y ensayar por etapas

Sólo después del checklist de `docs/VALIDATION.md`, cambia en `config.py`:

```python
DRY_RUN = False
```

Ejecuta una etapa; revisa video/batería y pulsa **t en la ventana OpenCV**:

```powershell
python main.py --stage hover
python main.py --stage horizontal
python main.py --stage align
python main.py --stage approach
python main.py --stage full
```

Cada comando es una sesión independiente, no se ejecutan todos a la vez:

| Etapa | Movimiento autorizado tras pulsar t |
|---|---|
| hover | Despegar y mantener RC cero; sin autonomía |
| horizontal | Sólo corrección LR; UD/FB/yaw cero |
| align | LR + UD; FB/yaw cero |
| approach | Alineación y avance; se frena al ratio cercano, nunca CROSS |
| full | Alineación, aproximación, CROSS temporizado, hover y aterrizaje |

`python main.py` equivale a `--stage full`, pero conserva el bloqueo DRY RUN por
configuración. `--dry-run` vuelve a bloquear vuelo sin editar configuración.
No existe un flag que anule DRY RUN para volar, ni vuelo headless.

## Parada y protecciones

- **q / ESC** en la ventana, cerrar la ventana principal o **Ctrl+C**: salir de
  autonomía, RC cero y aterrizaje si se intentó despegar; luego apagar stream y cerrar.
- En pleno `takeoff`, ESC sigue atendido y solicita RC cero. El ascenso SDK no se
  puede cancelar; se espera su respuesta/timeout y después se intenta aterrizar.
  No se usa `emergency()`, que cortaría motores en el aire.
- Antes del vuelo: conexión, batería mínima, frame real decodificado, telemetría
  fresca y armado manual. Durante vuelo: batería baja, video detenido, pérdida
  prolongada del gate, telemetría detenida, tiempo máximo o fallo del bucle abortan.
- SEARCH mantiene RC cero y no gira. Una detección aislada nunca mueve. APPROACH
  frena ante la primera pérdida y debe reconstruir estabilidad antes de avanzar.
- CROSS continúa si pierde el contorno, pero aborta ante fallo del stream o
  comunicaciones. Se envía RC continuamente desde un único hilo con watchdog.
- RC cero solicita hover; no garantiza posición fija ni frenado instantáneo.
  Si se pierde Wi-Fi, tampoco se garantiza entrega de cero/aterrizaje. Se necesita
  un operador, zona despejada, protecciones y un procedimiento físico de recuperación.

## Convención y límites

```text
error_x = (gate_center_x - frame_width/2) / (frame_width/2)
error_y = (frame_height/2 - gate_center_y) / (frame_height/2)
lr = KP_X * error_x
ud = KP_Y * error_y
```

X positivo = derecha; Y positivo = arriba. Kp ya produce unidades RC por unidad de
error; no se multiplica otra vez por 100. Deadband, saturación y EMA se aplican
en el controlador. Yaw siempre cero. Verifica ambos signos físicamente en las
etapas horizontal/align antes de permitir avance.

## Estructura

```text
tello_gates/
  main.py                  estados, CLI y ciclo de vida
  config.py                parámetros y validación
  gate_detector.py         HSV, contornos, errores y overlay
  controller.py            P + deadband + saturación + EMA
  video_source.py          captura BGR, telemetría, emisor RC y limpieza
  hsv_calibration.py       trackbars sin vuelo
  requirements.txt
  tests/test_detector.py   detector, control, estados e integración
  tests/test_safety.py     fallos y ciclo de vida con mocks
  samples/README.md
  samples/generate_sample.py
  docs/FASE_2.md
  docs/ARCHITECTURE.md
  docs/CALIBRATION.md
  docs/VALIDATION.md
```

## Límites de la validación

Las pruebas automatizadas verifican lógica y casos sintéticos, no precisión en
el robotario. Pendientes: imágenes reales etiquetadas, iluminación, perspectiva,
signo y respuesta física, latencia, distancia al disparar CROSS y duración real
necesaria para cruzar. HSV no identifica semánticamente gates ni evita obstáculos.

Referencia de API: [documentación oficial de DJITelloPy](https://djitellopy.readthedocs.io/en/latest/tello/).
El proyecto fija DJITelloPy 2.5.0 porque comprueba contra esa implementación la
conversión RGB→BGR y la frescura de telemetría mediante reemplazo del diccionario.
