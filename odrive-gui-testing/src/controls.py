from datetime import datetime
from typing import Any
import csv
import odrive
import odrive.enums as enums
from nicegui import ui
import odrive.utils as utils
import asyncio
import time
from typing import List
import threading
from typing import Optional
from typing import Tuple
import matplotlib.pyplot as plt

recording = False
start_time = None
data_buffer = []

def controls(odrv):
    modes = {
        0: 'voltage',
        1: 'torque',
        2: 'velocity',
        3: 'position',
    }

    input_modes = {
        0: 'inactive',
        1: 'through',
        2: 'v-ramp',
        3: 'p-filter',
        5: 'trap traj',
        6: 't-ramp',
        7: 'mirror',
    }

    states = {
        0: 'undefined',
        1: 'idle',
        8: 'loop',
    }



    #Begins recording process
    def record_data():
        global recording, start_time, data_buffer

        if recording:
            # Stop recording
            recording = False
            elapsed_time = datetime.now() - start_time
            print(f"Stopped recording. Elapsed time: {elapsed_time}")
            recording_button.text = 'Start Recording'
            save_data()
        else:
            # Start recording
            recording = True
            start_time = datetime.now()
            data_buffer = [] #Initiaize the data buffer to fill with data for certain period of time
            print("Started recording")
            recording_button.text = 'Stop Recording'
            thread = threading.Thread(target=recording_data) #Using threads to allow for a number of different methods to run while the save process is working
            thread.start()

    def save_data(): #Saves data once the Stop recoding button is pressed
        global data_buffer

        if len(data_buffer) > 0:
            filename = f"recorded_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            with open(filename, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Timestamp', 'Velocity Axis 1', 'I_G Axis 1', 'I_D Axis 1','Velocity Axis 0', 'I_G Axis 0', 'I_D Axis 0', 'I_Bus'])
                writer.writerows(data_buffer)

            print(f"Data saved to {filename}")
        else:
            print("No data to save.")

    def recording_data():
        global recording, data_buffer
        sample_interval = 0.00001  # Set the desired sample interval in seconds
        next_sample_time = time.monotonic() + sample_interval

        while recording:
            start_time = time.time()  # Record the start time for each sample

            # Collect data and add it to the buffer
            timestamp = datetime.now().strftime("%H:%M:%S.%f")
            velocity_0 = odrv.axis0.encoder.vel_estimate
            velocity_1 = odrv.axis1.encoder.vel_estimate
            i_g_0 = odrv.axis0.motor.current_control.Iq_measured
            i_d_0 = odrv.axis0.motor.current_control.Id_measured
            i_g_1 = odrv.axis1.motor.current_control.Iq_measured
            i_d_1 = odrv.axis1.motor.current_control.Id_measured
            i_bus = odrv.ibus

            data_point = [timestamp, velocity_1, i_g_1, i_d_1, velocity_0, i_g_0, i_d_0, i_bus]
            data_buffer.append(data_point)

            elapsed_time = time.monotonic() - start_time
            remaining_time = next_sample_time - time.monotonic()

            if remaining_time > 0:
                time.sleep(remaining_time)  # Wait for the remaining time until the next sample
            else:
                # If the sampling took longer than the desired interval, print a warning
                print("Warning: Sampling took longer than the desired interval.")

            # Adjust the next sample time to account for the actual elapsed time
            next_sample_time += sample_interval

            # If the sampling took longer than the desired interval, update the next sample time
            if elapsed_time > sample_interval:
                next_sample_time = time.monotonic() + sample_interval

    def show_errors():
        # Toggle error content. If errors are already displayed, hide them...
        if error_output.visible:
            error_output.visible = False
            return
        # ... else show them.
        error_output.visible = True

        errors = str(utils.format_errors(odrv, True))# Get the errors from the ODrive in format but in rich text converted to str
        # This would print fine in a console, but it's not really markdown-compatible yet (it'll print in a single line)
        # It is an indented list. To be markdown-compatible we need to add list points while respecting the indentation.
        # Additionally, the list elements can contain markdown characters which need to be escaped. However,
        # escaping f.ex. ABC_DEF => ABC\_DEF doesn't seem to work. therefore format each list entry as code with `...`
        errors = errors.splitlines()
        for i, e in enumerate(errors):
            # There might be a more pythonic way for separating the whitespace padding, but I couldn't think of one...
            j = 0
            while e[j].isspace():
                j += 1
            errors[i] = f"{e[:j]}- `{e[j:]}`"

        errors = "\n".join(errors)
        error_output.set_content(errors)  # Update the output widget with the error information

    #Axis Calibration sequence start
    def axis_calibration(axis):
        axis.requested_state = enums.AxisState.IDLE
        axis.requested_state = enums.AxisState.FULL_CALIBRATION_SEQUENCE
        while axis.current_state != enums.AxisState.IDLE: #Will check if the motor is idle, if is the time.sleep(1) will stop
            time.sleep(1)
    #Ensures nothing else interrupts the Axis calibration during use
    def start_calibration_0():
        axis_calibration(odrv.axis0)

    def start_calibration_1():
        axis_calibration(odrv.axis1)

    #All components at the top page of the GUI
    with ui.row().classes('items-center'):
        ui.label(f'SN {hex(odrv.serial_number).removeprefix("0x").upper()}')
        ui.label(f'HW {odrv.hw_version_major}.{odrv.hw_version_minor}.{odrv.hw_version_variant}')
        ui.label(f'FW {odrv.fw_version_major}.{odrv.fw_version_minor}.{odrv.fw_version_revision} ' +
                 f'{"(dev)" if odrv.fw_version_unreleased else ""}')
        voltage = ui.label()
        ui.timer(1.0, lambda: voltage.set_text(f'{odrv.vbus_voltage:.2f} V'))
        ui.button(on_click=lambda: odrv.save_configuration()).props('icon=save flat round').tooltip('Save configuration')
        recording_button = ui.button("Start Recording", on_click=record_data).props('icon=record_voice_over flat round')
        ui.button("Show Errors", on_click=show_errors).props('icon=bug_report flat round')
    # Print errors below the top line of components.
    with ui.row().classes('items-center'):
        error_output = ui.markdown()  # Create an output widget for displaying errors
        error_output.visible = False  # See show_errors for details

    with ui.row().classes('items-center'):
        ui.button("Axis 0 Calibration", on_click=lambda: start_calibration_0()).props('icon=build')
        ui.button("Axis 1 Calibration", on_click=lambda: start_calibration_1()).props('icon=build')
    #Method to bind each button to a function and return commands to the motor controller. Also allows to display important information of the motor
    def axis_column(a: int, axis: Any) -> None:
        ui.markdown(f'### Axis {a}')

        state = ui.label()
        power = ui.label()
        ui.timer(0.1, lambda: power.set_text(
            f'{axis.motor.current_control.Iq_measured * axis.motor.current_control.v_current_control_integral_q:.1f} W'))
        ui.timer(0.1, lambda: state.set_text(
            f'State - {axis_state_check(axis)} ({axis.current_state})'))

        async def update_y_axis_range(min, max):
            y_axis_range = [min, max]
            print(y_axis_range)
            await vel_push(y_axis_range)
            # iq_push(min, max)
            # id_push(min, max)
            # t_push(min, max)

        def axis_state_check(axis):
            if axis.current_state == 0:
                x = 'Undefined'
            elif axis.current_state == 1:
                x = 'Idle'
            elif axis.current_state == 2:
                x = 'Startup Sequence'
            elif axis.current_state == 3:
                x = 'Full Calibration Sequence'
            elif axis.current_state == 4:
                x = 'Motor Calibration'
            elif axis.current_state == 6:
                x = 'Encoder Index Search'
            elif axis.current_state == 7:
                x = 'Encoder Offset Calibration'
            elif axis.current_state == 8:
                x = 'Closed Loop Control'
            elif axis.current_state == 9:
                x = 'Lock in Spin'
            elif axis.current_state == 10:
                x = 'Encoder Dir Find'
            elif axis.current_state == 11:
                x = 'Homing'
            elif axis.current_state == 12:
                x = 'Encoder Hall Polarity Calibration'
            elif axis.current_state == 13:
                x = 'Encoder Hall Phase Calibration'

            return x

        ctr_cfg = axis.controller.config
        mtr_cfg = axis.motor.config
        enc_cfg = axis.encoder.config
        trp_cfg = axis.trap_traj.config

        with ui.row():
            mode = ui.toggle(modes).bind_value(ctr_cfg, 'control_mode')
            ui.toggle(states) \
                .bind_value_to(axis, 'requested_state', forward=lambda x: x or 0) \
                .bind_value_from(axis, 'current_state')

        with ui.row():
            with ui.card().bind_visibility_from(mode, 'value', value=1):
                ui.markdown('**Torque**')
                torque = ui.number('input torque', value=0)
                def send_torque(sign: int) -> None: axis.controller.input_torque = sign * float(torque.value)
                with ui.row():
                    ui.button(on_click=lambda: send_torque(-1)).props('round flat icon=remove')
                    ui.button(on_click=lambda: send_torque(0)).props('round flat icon=radio_button_unchecked')
                    ui.button(on_click=lambda: send_torque(1)).props('round flat icon=add')

            with ui.card().bind_visibility_from(mode, 'value', value=2):
                ui.markdown('**Velocity**')
                velocity = ui.number('input velocity', value=0)
                def send_velocity(sign: int) -> None: axis.controller.input_vel = sign * float(velocity.value)
                with ui.row():
                    ui.button(on_click=lambda: send_velocity(-1)).props('round flat icon=fast_rewind')
                    ui.button(on_click=lambda: send_velocity(0)).props('round flat icon=stop')
                    ui.button(on_click=lambda: send_velocity(1)).props('round flat icon=fast_forward')

            with ui.card().bind_visibility_from(mode, 'value', value=3):
                ui.markdown('**Position**')
                position = ui.number('input position', value=0)
                def send_position(sign: int) -> None: axis.controller.input_pos = sign * float(position.value)
                with ui.row():
                    ui.button(on_click=lambda: send_position(-1)).props('round flat icon=skip_previous')
                    ui.button(on_click=lambda: send_position(0)).props('round flat icon=exposure_zero')
                    ui.button(on_click=lambda: send_position(1)).props('round flat icon=skip_next')

            with ui.column():
                ui.number('pos_gain', format='%.3f').props('outlined').bind_value(ctr_cfg, 'pos_gain')
                ui.number('vel_gain', format='%.3f').props('outlined').bind_value(ctr_cfg, 'vel_gain')
                ui.number('vel_integrator_gain', format='%.3f').props('outlined').bind_value(ctr_cfg, 'vel_integrator_gain')
                if hasattr(ctr_cfg, 'vel_differentiator_gain'):
                    ui.number('vel_differentiator_gain', format='%.3f').props('outlined').bind_value(ctr_cfg, 'vel_differentiator_gain')

            with ui.column():
                ui.number('vel_limit', format='%.3f').props('outlined').bind_value(ctr_cfg, 'vel_limit')
                ui.number('enc_bandwidth', format='%.3f').props('outlined').bind_value(enc_cfg, 'bandwidth')
                ui.number('current_lim', format='%.1f').props('outlined').bind_value(mtr_cfg, 'current_lim')
                ui.number('cur_bandwidth', format='%.3f').props('outlined').bind_value(mtr_cfg, 'current_control_bandwidth')
                ui.number('torque_lim', format='%.1f').props('outlined').bind_value(mtr_cfg, 'torque_lim')
                ui.number('requested_cur_range', format='%.1f').props('outlined').bind_value(mtr_cfg, 'requested_current_range')

        input_mode = ui.toggle(input_modes).bind_value(ctr_cfg, 'input_mode')
        with ui.row():
            ui.number('inertia', format='%.3f').props('outlined') \
                .bind_value(ctr_cfg, 'inertia') \
                .bind_visibility_from(input_mode, 'value', backward=lambda m: m in [2, 3, 5])
            ui.number('velocity ramp rate', format='%.3f').props('outlined') \
                .bind_value(ctr_cfg, 'vel_ramp_rate') \
                .bind_visibility_from(input_mode, 'value', value=2)
            ui.number('input filter bandwidth', format='%.3f').props('outlined') \
                .bind_value(ctr_cfg, 'input_filter_bandwidth') \
                .bind_visibility_from(input_mode, 'value', value=3)
            ui.number('trajectory velocity limit', format='%.3f').props('outlined') \
                .bind_value(trp_cfg, 'vel_limit') \
                .bind_visibility_from(input_mode, 'value', value=5)
            ui.number('trajectory acceleration limit', format='%.3f').props('outlined') \
                .bind_value(trp_cfg, 'accel_limit') \
                .bind_visibility_from(input_mode, 'value', value=5)
            ui.number('trajectory deceleration limit', format='%.3f').props('outlined') \
                .bind_value(trp_cfg, 'decel_limit') \
                .bind_visibility_from(input_mode, 'value', value=5)
            ui.number('torque ramp rate', format='%.3f').props('outlined') \
                .bind_value(ctr_cfg, 'torque_ramp_rate') \
                .bind_visibility_from(input_mode, 'value', value=6)
            ui.number('mirror ratio', format='%.3f').props('outlined') \
                .bind_value(ctr_cfg, 'mirror_ratio') \
                .bind_visibility_from(input_mode, 'value', value=7)
            ui.toggle({0: 'axis 0', 1: 'axis 1'}) \
                .bind_value(ctr_cfg, 'axis_to_mirror') \
                .bind_visibility_from(input_mode, 'value', value=7)

        #Allows us to Show the graphs of position, velocity, torque and current
        async def pos_push() -> None:
            #Allows for the actual recording of the values while other processes take place. All these datapoints are recorded and appended to an empty data buffe which we will then save.
            if recording:
                timestamp = datetime.now()
                velocity = axis.encoder.vel_estimate
                i_g = axis.motor.current_control.Iq_measured
                i_d = axis.motor.current_control.Id_measured
                i_bus = axis.motor.current_control.Ibus

                data_row = [timestamp, velocity, i_g, i_d, i_bus]
                data_buffer.append(data_row)

            pos_plot.push([datetime.now()], [[axis.controller.input_pos], [axis.encoder.pos_estimate]])

            await pos_plot.view.update()


        #All the options for the plots
        async def vel_push(y_axis_range: Optional[Tuple[float, float]] = None) -> None:
            vel_plot.push([datetime.now()], [[axis.controller.input_vel], [axis.encoder.vel_estimate]])
            await vel_plot.view.update()

        async def id_push(y_axis_range: Optional[Tuple[float, float]] = None) -> None:
            #ax = id_plot.view.ax
            #ax.set_ylim(*y_axis_range)
            id_plot.push([datetime.now()], [[axis.motor.current_control.Id_setpoint], [axis.motor.current_control.Id_measured]])
            await id_plot.view.update()

        async def iq_push(y_axis_range: Optional[Tuple[float, float]] = None) -> None:
            #ax = iq_plot.view.ax
            #ax.set_ylim(*y_axis_range)
            iq_plot.push([datetime.now()], [[axis.motor.current_control.Iq_setpoint], [axis.motor.current_control.Iq_measured]])
            await iq_plot.view.update()

        async def t_push(y_axis_range: Optional[Tuple[float, float]] = None) -> None:
            #ax = t_plot.view.ax
            #ax.set_ylim(*y_axis_range)
            t_plot.push([datetime.now()], [[axis.motor.fet_thermistor.temperature]])
            await t_plot.view.update()


        '''custom_range_checkbox = ui.checkbox('Custom Y-Axis Range')
        custom_y_min = ui.number('Y-Min', value=0).bind_visibility_from(custom_range_checkbox, 'value')
        custom_y_max = ui.number('Y-Max', value=10).bind_visibility_from(custom_range_checkbox, 'value')
        custom_range_button = ui.button('Set range', on_click=update_y_axis_range(custom_y_min, custom_y_max)).bind_visibility_from(custom_range_checkbox, 'value')
        # Set the default value of the checkbox to False (no custom range)
        custom_range_checkbox.value = False'''

        #Characteristics of the plots
        with ui.row():
            pos_check = ui.checkbox('Position plot')
            pos_plot = ui.line_plot(n=2, update_every=0.125).with_legend(['input_pos', 'pos_estimate'], loc='upper left', ncol=2)
            pos_timer = ui.timer(0.05, pos_push)
            pos_check.bind_value_to(pos_plot, 'visible').bind_value_to(pos_timer, 'active')

            vel_check = ui.checkbox('Velocity plot')
            vel_plot = ui.line_plot(n=2, update_every=0.125).with_legend(['input_vel', 'vel_estimate'], loc='upper left', ncol=2)
            vel_timer = ui.timer(0.05, vel_push)
            vel_check.bind_value_to(vel_plot, 'visible').bind_value_to(vel_timer, 'active')

            id_check = ui.checkbox('Id plot')
            id_plot = ui.line_plot(n=2, update_every=0.125).with_legend(['Id_setpoint', 'Id_measured'], loc='upper left', ncol=2)
            id_timer = ui.timer(0.05, id_push)
            id_check.bind_value_to(id_plot, 'visible').bind_value_to(id_timer, 'active')

            iq_check = ui.checkbox('Iq plot')
            iq_plot = ui.line_plot(n=2, update_every=0.125).with_legend(['Iq_setpoint', 'Iq_measured'], loc='upper left', ncol=2)
            iq_timer = ui.timer(0.05, iq_push)
            iq_check.bind_value_to(iq_plot, 'visible').bind_value_to(iq_timer, 'active')

            t_check = ui.checkbox('Temperature plot')
            t_plot = ui.line_plot(n=1, update_every=0.125)
            t_timer = ui.timer(0.05, t_push)
            t_check.bind_value_to(t_plot, 'visible').bind_value_to(t_timer, 'active')

    with ui.row():
        for a, axis in enumerate([odrv.axis0, odrv.axis1]):
            with ui.card(), ui.column():
                axis_column(a, axis)









