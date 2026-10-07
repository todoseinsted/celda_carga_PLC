# Lectura de celdas de carga con Raspberry PLC 19R

Programa de lectura para un sistema de pesaje formado por:

- 4 celdas de carga de 5 t conectadas a una caja sumadora.
- Transmisor DY500 configurado con salida de 4-20 mA.
- Acondicionador Weidmuller ACT20M configurado de 4-20 mA a 0-10 V.
- Raspberry PLC 19R V6, utilizando la entrada analogica `I0.5`.

La capacidad nominal del conjunto es de 20.000 kg brutos cuando la carga se
distribuye correctamente. La carga util es menor porque incluye el peso propio
del volquete y debe respetar los limites mecanicos de cada apoyo.

El programa es exclusivamente de lectura. No acciona reles ni otras salidas del
PLC.

## Cadena de senal

```text
4 celdas de carga
        |
        v
Caja sumadora de 4 canales
        |
        v
DY500: 4-20 mA
        |
        v
Weidmuller ACT20M: 4-20 mA -> 0-10 V
        |
        v
Raspberry PLC 19R: I0.5
```

En el Raspberry PLC, el conversor ADC entrega valores entre 0 y 4095:

- 0 cuentas = 0 V = 4 mA en la entrada del Weidmuller.
- 4095 cuentas = 10 V = 20 mA en la entrada del Weidmuller.

Antes de una calibracion real, el programa usa provisionalmente
`0-4095 = 0-20.000 kg`. Esta estimacion no debe utilizarse como pesaje definitivo.

## Cableado principal

### DY500 al Weidmuller

Conectar la salida analogica del DY500 respetando la polaridad indicada por los
dos fabricantes. En el DY500:

```text
AO = salida analogica
AG = retorno analogico
```

El DY500 debe estar configurado para salida de 4-20 mA y el ACT20M para entrada
de 4-20 mA y salida de 0-10 V.

### Weidmuller al PLC

Para el canal de salida 1 del ACT20M:

```text
ACT20M salida positiva -> I0.5
ACT20M salida negativa -> GND/COM analogico del PLC
```

Comprobar con un multimetro la tension entre `I0.5` y el comun analogico antes
de iniciar la aplicacion. No superar 10 V.

## Requisitos

- Raspberry PLC 19R V6.
- Python 3.
- Utilidad de lectura analogica de Industrial Shields:

```text
/home/RaspPLC1/test/RPIPLC_V6/RPIPLC_19R/get-analog-input
```

El programa utiliza solamente modulos de la biblioteca estandar de Python.

## Instalacion

Copiar `peso_volquete.py` al PLC, por ejemplo dentro de `Ensayos`:

```bash
scp peso_volquete.py USUARIO@DIRECCION_DEL_PLC:/home/USUARIO/Ensayos/
ssh USUARIO@DIRECCION_DEL_PLC
chmod 755 /home/USUARIO/Ensayos/peso_volquete.py
```

La ruta del driver y del archivo de calibracion pueden cambiarse mediante
opciones de linea de comandos.

## Uso

Lectura continua:

```bash
/home/RaspPLC1/Ensayos/peso_volquete.py
```

Una sola lectura:

```bash
/home/RaspPLC1/Ensayos/peso_volquete.py --once
```

Salida en JSON, util para integrar con otra aplicacion:

```bash
/home/RaspPLC1/Ensayos/peso_volquete.py --json
```

Ejemplo de salida:

```text
2026-10-07T17:08:20-03:00 | I0.5 | raw=3.00 | 0.007 V |
equiv=4.012 mA | peso=14.7 kg (estimado) |
ESTIMADO_FALTA_CALIBRACION_CON_PESO
```

## Calibracion de dos puntos

La calibracion debe realizarse despues del montaje mecanico, el balance de las
cuatro esquinas y el calentamiento normal de los equipos.

### 1. Cero

Con el volquete vacio, completamente apoyado y estable:

```bash
/home/RaspPLC1/Ensayos/peso_volquete.py --hacer-cero
```

Esta operacion invalida deliberadamente cualquier segundo punto anterior, para
evitar usar una pendiente que ya no corresponda al nuevo montaje.

### 2. Peso conocido

Colocar un peso conocido. Cuanto mayor sea el peso patron, mejor sera la
calibracion; se recomienda al menos el 10 % del alcance cuando sea posible.

Ejemplo para 1.000 kg:

```bash
/home/RaspPLC1/Ensayos/peso_volquete.py --calibrar-peso 1000
```

La calibracion queda almacenada localmente en:

```text
/home/RaspPLC1/Ensayos/peso_calibracion.json
```

Este archivo no se versiona porque corresponde a una instalacion fisica
particular.

Consultar la calibracion guardada:

```bash
/home/RaspPLC1/Ensayos/peso_volquete.py --mostrar-config
```

## Opciones principales

```text
--channel I0.5          Entrada analogica utilizada.
--once                  Realiza una lectura y termina.
--json                  Entrega cada lectura como JSON.
--interval SEGUNDOS     Intervalo entre lecturas.
--samples N             Cantidad impar de muestras para el filtro de mediana.
--hacer-cero             Guarda la lectura actual como cero.
--calibrar-peso KG      Guarda el segundo punto de calibracion.
--full-scale-kg KG      Alcance nominal usado antes de calibrar.
--allow-negative        Permite mostrar pesos negativos.
```

Ver todas las opciones:

```bash
/home/RaspPLC1/Ensayos/peso_volquete.py --help
```

## Caja sumadora

Los cuatro potenciometros no se utilizan para ajustar el cero general. Cada
potenciometro modifica ligeramente la contribucion de una celda para igualar la
respuesta de las cuatro esquinas.

Procedimiento recomendado:

1. Terminar primero la instalacion mecanica.
2. Colocar el mismo peso sobre cada esquina, siempre en una posicion equivalente.
3. Registrar las cuatro lecturas.
4. Ajustar solamente los canales que difieran, con movimientos muy pequenos.
5. Repetir todas las posiciones hasta obtener respuestas equivalentes.
6. Hacer finalmente el cero y la calibracion con peso conocido.

No se debe corregir con los potenciometros un problema mecanico como una base
desnivelada, un apoyo trabado o una fuerza lateral.

## Instalacion mecanica de los modulos

- Las bases superior e inferior deben quedar firmes, planas y paralelas.
- La fuerza debe aplicarse verticalmente y centrada sobre el boton de carga.
- Las cuatro bases deben quedar coplanares, sin balanceo.
- La tuerca o bloqueo de transporte debe liberarse para pesar.
- Los tornillos antilevantamiento no deben soportar peso durante la operacion
  normal; deben conservar la holgura especificada por el fabricante.
- Las restricciones laterales deben controlar movimientos horizontales sin
  bloquear la pequena deformacion vertical necesaria para medir.
- Ninguna bisagra, cilindro, manguera, tope o apoyo auxiliar debe derivar parte
  del peso por fuera de las cuatro celdas.
- Los cables deben quedar protegidos, sin tension mecanica y con entrada de agua
  controlada.
- El pesaje debe realizarse con el vehiculo detenido, en una superficie nivelada
  y con el volquete completamente apoyado.

En un volquete, las bisagras traseras y el sistema hidraulico requieren especial
atencion: si sostienen parte de la carga durante el pesaje, el resultado sera
menor que el peso real aunque la calibracion electrica sea correcta.

## Diagnostico

| Sintoma | Comprobacion inicial |
|---|---|
| Lectura cercana a 0 cuentas | Medir la salida 0-10 V del ACT20M y verificar el comun analogico. |
| 4095 cuentas permanentes | Entrada saturada o tension superior al alcance. |
| El peso no cambia | Revisar DY500, configuracion del ACT20M y camino mecanico de carga. |
| El peso cambia en sentido contrario | Revisar polaridad de la senal de las celdas. |
| Cada esquina mide diferente | Revisar nivelacion y trabas antes de ajustar la caja sumadora. |
| El cero deriva | Revisar apoyos, temperatura, humedad, cables y fuerzas laterales. |

## Seguridad

- No trabajar debajo de un volquete sostenido solamente por el circuito
  hidraulico.
- Utilizar bloqueo mecanico, calzas y procedimientos de trabajo seguro.
- No exceder la capacidad individual de ninguna celda aunque la suma teorica sea
  de 20 t.
- Considerar impactos y cargas dinamicas; la capacidad nominal de pesaje no es
  automaticamente la capacidad estructural segura del vehiculo.

