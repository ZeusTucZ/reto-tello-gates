# Calibración en robotario

Todos los valores de `config.py` son puntos de partida sin ensayo físico.
Mantén `DRY_RUN=True` hasta verificar detección y signos. Modifica una familia de
parámetros por prueba y registra valor anterior, nuevo valor, iluminación, FPS,
distancia, batería, resultado y motivo. Vuelve a DRY RUN al terminar la sesión.

## 1. HSV

Con Tello en el piso frente al marco, ejecuta `python hsv_calibration.py`.
Ajusta H min/max para el color, después S para excluir grises y V para excluir
sombras. Conserva todo el marco sin unirlo a objetos del fondo. Pulsa `p` y copia
`HSV_MIN` y `HSV_MAX` a `config.py`. H usa 0..179; S/V usan 0..255. Prueba varias
distancias y ángulos bajo la iluminación final. Una sola franja HSV no cubre rojo
a ambos lados de H=0/179. No cambies RGB/BGR: Tello ya se convierte en la captura.

## 2. Área mínima y geometría

Ejecuta `python main.py --dry-run`. Todas las imágenes se escalan manteniendo
aspecto a `PROCESS_WIDTH=640`; `MIN_CONTOUR_AREA` y `MIN_GATE_SIZE` se refieren a
esa imagen procesada. El área es del contorno exterior, incluyendo el hueco,
no el número de píxeles coloreados del marco. Cambiar ancho exige recalibrar áreas
y tamaños: aproximadamente área por escala² y tamaño por escala.

Sube `MIN_CONTOUR_AREA`/`MIN_GATE_SIZE` para excluir manchas pequeñas, sin perder
el gate a la distancia inicial. Ajusta `ASPECT_RATIO_TOLERANCE` si rechaza una
perspectiva moderada; no abras tanto el intervalo que admita franjas alargadas.
`MIN_RECTANGULARITY`, vértices, convexidad y hueco reducen falsos positivos.
Mantén `REQUIRE_HOLE=True` para un marco. Bajar esa exigencia admite paneles y
requiere nueva validación con negativos.

Usa apertura pequeña para quitar ruido y cierre pequeño para unir discontinuidades.
Un kernel grande puede borrar el marco o cerrar el hueco. Ajusta
`MORPH_KERNEL_SIZE`, `MORPH_OPEN_ITERATIONS`, `MORPH_CLOSE_ITERATIONS` y revisa la máscara.
Si hay falsos positivos: primero mejora HSV/fondo, luego área/geometría y finalmente
estabilidad; no intentes compensar un detector incorrecto con ganancias menores.

## 3. Deadband y estabilidad

Coloca gate centrado y observa jitter de `error_x/y`. Elige `DEADBAND_X/Y` algo
mayor al ruido observado, pero con margen físico suficiente para hélices y marco.
Deadband demasiado pequeña: constantes correcciones/cambios de signo estando
centrado y nunca se acumulan frames alineados. Demasiado grande: el dron empieza
a avanzar con un error visible que puede ser peligroso cerca del gate.

`DETECTED_FRAMES`, `ALIGNED_FRAMES`, `CROSS_STABLE_FRAMES` cuentan frames procesados,
no segundos. Mide FPS real: N frames a f FPS tardan aproximadamente N/f segundos.
`MAX_CENTER_JUMP` y `MAX_SIZE_CHANGE` impiden aceptar alternancia entre objetos,
pero también pueden rechazar movimiento rápido. `LOST_FRAMES` cambia a SEARCH;
el avance ya se detiene desde la primera pérdida. Reaparición exige reconstruir
estabilidad y alineación. Ajusta `REALIGN_MULTIPLIER` para histéresis moderada.

## 4. Kp

Tras aprobar hover, prueba `--stage horizontal`, después `--stage align`.
Empieza con desplazamientos pequeños del gate respecto al centro. `KP_X/Y`
producen unidades RC por unidad de error normalizado, sin factor 100 adicional.

- Kp bajo: error sostenido con corrección débil o tan pequeña que redondea a cero.
- Kp alto: sobrepaso, oscilaciones o cambios bruscos; reduce Kp y revisa latencia.
- EMA_ALPHA menor suaviza pero añade retardo. No uses un suavizado muy lento para
  ocultar mala segmentación. Con valor 1 no hay suavizado.

No subas ambos Kp y velocidad máxima a la vez. Si el signo físico es incorrecto,
detén la prueba y revisa la convención y orientación de cámara antes de continuar.

## 5. Máximas velocidades

Calibra `MAX_LR_SPEED`, `MAX_UD_SPEED` y el límite global `MAX_RC_SPEED` en espacio
abierto. Valores iniciales bajos pueden no vencer deriva; incrementa gradualmente
sólo con margen y observador. El límite global restringe todos los ejes además
del límite SDK [-100,100]. No interpretes estas unidades como cm/s medidos.

## 6. Aproximación

Usa `--stage approach` con `APPROACH_SPEED` baja. Comprueba que sigue corrigiendo
X/Y y que ante desalineación o pérdida FB cae a cero. La inercia real puede mantener
movimiento aunque el comando sea cero: mide tiempo/distancia de frenado.
Esta etapa se detiene al threshold de proximidad y nunca ejecuta CROSS.

## 7. Proximidad

Con el dron en el piso a distancias medidas, registra `gate_width/frame_width`.
Selecciona `CLOSE_WIDTH_RATIO` a una distancia donde el marco aún esté completo,
exista margen de alineación y sea posible cruzar con el movimiento planificado.
El bbox es del marco exterior y el ancho nominal de 1 m no es el hueco libre.

Threshold demasiado bajo: CROSS comienza lejos y puede acabar antes del gate.
Demasiado alto: comienza tarde, el marco se recorta, pierde detección o colisiona
antes de entrar a CROSS. La perspectiva y la inclinación cambian el ratio sin
cambiar necesariamente la distancia: úsalo sólo como indicador calibrado.

## 8. CROSS

Sólo después de aprobar APPROACH, configura `CROSS_SPEED` y `CROSS_DURATION`.
Mide avance y frenado en espacio abierto primero. Prueba cruce con observador y
zona libre detrás del gate, incluyendo margen de deriva. No calcules distancia
simplemente multiplicando unidades RC por tiempo: no es una velocidad calibrada.
Durante CROSS, LR/UD/yaw son cero y se acepta perder el contorno; fallo del stream,
telemetría, batería o tecla de parada todavía abortan. Ajusta `DONE_HOVER_SECONDS`
para estabilización antes de aterrizar sin invadir obstáculos posteriores.

## Inventario exacto de parámetros por revisar

| Grupo | Valores de `config.py` |
|---|---|
| Color | `HSV_MIN`, `HSV_MAX` |
| Escala y geometría | `PROCESS_WIDTH`, `MIN_CONTOUR_AREA`, `MIN_GATE_SIZE`, `ASPECT_RATIO_TOLERANCE`, `MIN_RECTANGULARITY`, `POLYGON_EPSILON`, `MIN_POLYGON_VERTICES`, `MAX_POLYGON_VERTICES`, `REQUIRE_HOLE`, `MIN_HOLE_AREA_RATIO`, `MAX_HOLE_AREA_RATIO` |
| Morfología | `MORPH_KERNEL_SIZE`, `MORPH_OPEN_ITERATIONS`, `MORPH_CLOSE_ITERATIONS` |
| Estabilidad | `DETECTED_FRAMES`, `ALIGNED_FRAMES`, `CROSS_STABLE_FRAMES`, `LOST_FRAMES`, `MAX_CENTER_JUMP`, `MAX_SIZE_CHANGE`, `REALIGN_MULTIPLIER` |
| Control P | `KP_X`, `KP_Y`, `DEADBAND_X`, `DEADBAND_Y`, `EMA_ALPHA`, `MAX_LR_SPEED`, `MAX_UD_SPEED` |
| Avance | `APPROACH_SPEED`, `CROSS_SPEED`, `CROSS_DURATION`, `CLOSE_WIDTH_RATIO`, `DONE_HOVER_SECONDS` |
| Seguridad | `MIN_TAKEOFF_BATTERY`, `MIN_FLIGHT_BATTERY`, `MAX_RC_SPEED`, `GATE_LOSS_TIMEOUT`, `FRAME_TIMEOUT`, `TELEMETRY_TIMEOUT`, `PRE_FLIGHT_TIMEOUT`, `MAX_FLIGHT_SECONDS`, `TAKEOFF_SETTLE_SECONDS`, `COMMAND_TIMEOUT` |
| Frecuencia y SDK | `CONTROL_HZ`, `SDK_COMMAND_TIMEOUT`, `SDK_TAKEOFF_TIMEOUT`, `SDK_RETRIES`, `LOCAL_VIDEO_FPS_FALLBACK` |
| Operación/visualización | `DRY_RUN`, `SHOW_MASK`, `HUD_LOG_INTERVAL` |

Los parámetros de seguridad se revisan según latencia y procedimiento del robotario;
no se deben alargar timeouts sólo para ocultar pérdidas frecuentes. Los últimos
valores de operación son opciones, no magnitudes físicas a estimar.
