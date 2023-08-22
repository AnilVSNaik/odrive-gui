# ODrive GUI

A web-based GUI to tweak and debug the ODrive motor controller.
It also comes packaged in a Docker image for easy usage.

<img src="https://github.com/zauberzeug/odrive-gui/raw/main/screenshot.png" width="100%">

## Usage

Install required packages through a terminal

```bash
python3 -m pip install requirements.txt
```

and start the app in a terminal:

```bash
python3 src/main.py
```

and access the interface at http://localhost:8080/.
It is convenient (but insecure) to use the `--privileged` parameter to allow access to USB.
You can also provide only the device you want to use with `--device=/dev/ttyUSB0` or similar.
