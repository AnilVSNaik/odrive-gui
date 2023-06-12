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

    # New function to save data as CSV
    recording = False  # Flag to indicate if data recording is active
    start_time = None  # Timestamp when recording started
    data_buffer = []  # Buffer to store recorded data

    def record_data():
        nonlocal recording, start_time

        if recording:
            # Stop recording
            recording = False
            elapsed_time = datetime.now() - start_time
            print(f"Stopped recording. Elapsed time: {elapsed_time}")
            save_data()
        else:
            # Start recording
            recording = True
            start_time = datetime.now()
            recording_data()
            print("Started recording.")

    #Implement save start and save end
    def recording_data():
        global data_buffer
        # Get the current timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Get the velocity data points, i_g, i_d, and i_bus
        velocity = odrv.Encoder.vel_estimate
        i_g = odrv.motor.CurrentControl.Iq_measured
        i_d = odrv.motor.CurrentControl.Id_measured
        i_bus = odrv.ibus

        # Append the data to the buffer
        data_buffer.append([timestamp, velocity, i_g, i_d, i_bus])
    ui.markdown('## ODrive GUI')

    def save_data():
        global data_buffer

        if len(data_buffer) > 0:
            # Get the file name based on the current timestamp
            file_name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S.csv")

            # Save the data to a CSV file
            with open(file_name, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(['Timestamp', 'Velocity', 'I_g', 'I_d', 'I_bus'])  # Write the header
                writer.writerows(data_buffer)  # Write the data rows

            # Clear the data buffer
            data_buffer = []
    #Potential for input speeds through txt file or someother

    from typing import List

    def format_errors(odrv, clear=False) -> str:
        is_legacy_firmware = (odrv.fw_version_major, odrv.fw_version_minor, odrv.fw_version_revision) <= (0, 5, 4)
        '''if is_legacy_firmware:
            return odrive.legacy.format_errors(odrv, clear)'''

        lines = []

        axes = [(name, getattr(odrv, name)) for name in dir(odrv) if name.startswith('axis')]
        axes.sort()

        def decode_flags(val, enum_type):
            errorcodes = {v.value: str(v) for v in enum_type}
            if val == 0:
                return "no error"
            else:
                error_strings = [errorcodes.get((1 << bit), 'UNKNOWN ERROR: 0x{:08X}'.format(1 << bit))
                                 for bit in range(64) if val & (1 << bit) != 0]
                return "Error(s): " + ", ".join(error_strings)

        def decode_enum(val, enum_type):
            errorcodes = {v.value: str(v) for v in enum_type}
            return errorcodes.get(val, 'Unknown value: ' + str(val))

        def decode_drv_fault(axis, val):
            if val == 0:
                return "none"
            elif not hasattr(axis, '_metadata'):
                return "metadata not loaded"
            else:
                return odrive.utils.decode_drv_faults(axis._metadata['drv'], val)

        def dump_item(indent, name, obj, path, decoder):
            prefix = indent + name.strip('0123456789') + ": "
            for elem in path.split('.'):
                if not hasattr(obj, elem):
                    return ""
                obj = getattr(obj, elem)

            lines = decoder(obj)
            lines = [indent + name + ": " + str(lines)] + [
                indent + "  " + line
                for line in lines[1:]
            ]
            return "\n".join(lines)

        lines.append(dump_item("", "system", odrv, 'error', lambda x: decode_flags(x, odrive.enums.ODriveError)))

        for name, axis in axes:
            lines.append(name)
            lines.append(dump_item("  ", 'error', axis, 'error', lambda x: decode_flags(x, odrive.enums.AxisError)))
            lines.append(dump_item("  ", 'active_errors', axis, 'active_errors',
                                   lambda x: decode_flags(x, odrive.enums.ODriveError)))
            lines.append(dump_item("  ", 'disarm_reason', axis, 'disarm_reason',
                                   lambda x: decode_flags(x, odrive.enums.ODriveError)))
            lines.append(dump_item("  ", 'procedure_result', axis, 'procedure_result',
                                   lambda x: decode_enum(x, odrive.enums.ProcedureResult)))
            lines.append(dump_item("  ", 'last_drv_fault', axis, 'last_drv_fault', lambda x: decode_drv_fault(axis, x)))

        if hasattr(odrv, 'issues') and hasattr(odrv.issues, 'length') and hasattr(odrv.issues, 'get'):
            if odrv.issues.length == 0:
                lines.append("internal issues: none")
            else:
                issues = [odrv.issues.get(i) for i in range(odrv.issues.length)]
                lines.append("internal issues: " + str(odrv.issues.length))
                lines.append("details for bug report: " + str(issues))

        if clear:
            odrv.clear_errors()

        return "\n".join(lines)

    def show_errors():
        errors = str(utils.format_errors(odrv, True))# Get the errors from the ODrive in format but in rich text converted to str
        error_output.set_content(errors)  # Update the output widget with the error information

    def axis_calibration(axis):
        axis.requested_state = enums.AxisState.IDLE
        axis.requested_state = enums.AxisState.FULL_CALIBRATION_SEQUENCE

    def start_calibration():
        axis_calibration(odrv.axis0)
        time.sleep(30)
        axis_calibration(odrv.axis1)
        time.sleep(30)

    #Add two buttons or 1 button for axis calibration
    with ui.row().classes('items-center'):
        ui.label(f'SN {hex(odrv.serial_number).removeprefix("0x").upper()}')
        ui.label(f'HW {odrv.hw_version_major}.{odrv.hw_version_minor}.{odrv.hw_version_variant}')
        ui.label(f'FW {odrv.fw_version_major}.{odrv.fw_version_minor}.{odrv.fw_version_revision} ' +
                 f'{"(dev)" if odrv.fw_version_unreleased else ""}')
        voltage = ui.label()
        ui.timer(1.0, lambda: voltage.set_text(f'{odrv.vbus_voltage:.2f} V'))
        ui.button(on_click=lambda: odrv.save_configuration()).props('icon=save flat round').tooltip('Save configuration')
        ui.button("Start/Stop Recording", on_click=record_data).props('icon=record_voice_over flat round')
        ui.button("Show Errors", on_click=show_errors).props('icon=bug_report flat round')
        error_output = ui.markdown()  # Create an output widget for displaying errors
        ui.button("Axis Calibration", on_click=lambda: start_calibration()).props('icon=build')


    def axis_column(a: int, axis: Any) -> None:
        ui.markdown(f'### Axis {a}')

        power = ui.label()
        ui.timer(0.1, lambda: power.set_text(
            f'{axis.motor.current_control.Iq_measured * axis.motor.current_control.v_current_control_integral_q:.1f} W'))

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
        '''async def pos_push() -> None:
            pos_plot.push([datetime.now()], [[axis.controller.input_pos], [axis.encoder.pos_estimate]])
            await pos_plot.view.update()
        pos_check = ui.checkbox('Position plot')
        pos_plot = ui.line_plot(n=2, update_every=10).with_legend(['input_pos', 'pos_estimate'], loc='upper left', ncol=2)
        pos_timer = ui.timer(0.05, pos_push)
        pos_check.bind_value_to(pos_plot, 'visible').bind_value_to(pos_timer, 'active')'''

        #Add autoscale or specify the y-axis and increase efficiency
        async def pos_push() -> None:
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

        async def vel_push() -> None:
            vel_plot.push([datetime.now()], [[axis.controller.input_vel], [axis.encoder.vel_estimate]])
            await vel_plot.view.update()
        vel_check = ui.checkbox('Velocity plot')
        vel_plot = ui.line_plot(n=2, update_every=5).with_legend(['input_vel', 'vel_estimate'], loc='upper left', ncol=2)
        vel_timer = ui.timer(0.05, vel_push)
        vel_check.bind_value_to(vel_plot, 'visible').bind_value_to(vel_timer, 'active')

        async def id_push() -> None:
            id_plot.push([datetime.now()], [[axis.motor.current_control.Id_setpoint], [axis.motor.current_control.Id_measured]])
            await id_plot.view.update()
        id_check = ui.checkbox('Id plot')
        id_plot = ui.line_plot(n=2, update_every=10).with_legend(['Id_setpoint', 'Id_measured'], loc='upper left', ncol=2)
        id_timer = ui.timer(0.05, id_push)
        id_check.bind_value_to(id_plot, 'visible').bind_value_to(id_timer, 'active')

        async def iq_push() -> None:
            iq_plot.push([datetime.now()], [[axis.motor.current_control.Iq_setpoint], [axis.motor.current_control.Iq_measured]])
            await iq_plot.view.update()
        iq_check = ui.checkbox('Iq plot')
        iq_plot = ui.line_plot(n=2, update_every=10).with_legend(['Iq_setpoint', 'Iq_measured'], loc='upper left', ncol=2)
        iq_timer = ui.timer(0.05, iq_push)
        iq_check.bind_value_to(iq_plot, 'visible').bind_value_to(iq_timer, 'active')

        async def t_push() -> None:
            t_plot.push([datetime.now()], [[axis.motor.fet_thermistor.temperature]])
            await t_plot.view.update()
        t_check = ui.checkbox('Temperature plot')
        t_plot = ui.line_plot(n=1, update_every=10)
        t_timer = ui.timer(0.05, t_push)
        t_check.bind_value_to(t_plot, 'visible').bind_value_to(t_timer, 'active')

    with ui.row():
        for a, axis in enumerate([odrv.axis0, odrv.axis1]):
            with ui.card(), ui.column():
                axis_column(a, axis)
