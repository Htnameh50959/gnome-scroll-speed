import GObject from 'gi://GObject';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Clutter from 'gi://Clutter';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {QuickSlider, SystemIndicator} from 'resource:///org/gnome/shell/ui/quickSettings.js';

// Slider is logarithmic: left = MIN, middle = 1x, right = MAX.
const MIN = 0.2;
const MAX = 5.0;
const CONFIG_DIR = GLib.build_filenamev([GLib.get_user_config_dir(), 'scroll-speed']);
const CONFIG_FILE = GLib.build_filenamev([CONFIG_DIR, 'factor']);

const toFactor = v => {
    const f = MIN * Math.pow(MAX / MIN, v);
    return Math.abs(f - 1) < 0.04 ? 1 : Math.round(f * 100) / 100;
};
const toValue = f => Math.log(f / MIN) / Math.log(MAX / MIN);

function readFactor() {
    try {
        const [, bytes] = GLib.file_get_contents(CONFIG_FILE);
        const f = parseFloat(new TextDecoder().decode(bytes));
        if (Number.isFinite(f))
            return Math.min(MAX, Math.max(MIN, f));
    } catch (e) {}
    return 1;
}

function daemonRunning() {
    try {
        const [, bytes] = GLib.file_get_contents('/proc/bus/input/devices');
        return new TextDecoder().decode(bytes).includes('Name="scroll-speedd');
    } catch (e) {
        return false;
    }
}

const ScrollSlider = GObject.registerClass(
class ScrollSlider extends QuickSlider {
    _init() {
        super._init({
            iconName: 'input-mouse-symbolic',
            iconReactive: true,
            iconLabel: 'Reset scroll speed',
        });
        this.slider.accessible_name = 'Scroll speed';

        this._label = new St.Label({
            style_class: 'scroll-speed-label',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this.child.insert_child_below(this._label, this._menuButton);

        this._factor = readFactor();
        this.slider.value = toValue(this._factor);
        this._updateLabel();

        this.slider.connect('notify::value', () => {
            this._factor = toFactor(this.slider.value);
            this._updateLabel();
            this._scheduleSave();
        });
        this.connect('icon-clicked', () => {
            this.slider.value = toValue(1);
        });
    }

    _updateLabel(running = true) {
        this._label.text = running ? `${this._factor.toFixed(2)}×` : 'no daemon';
        if (running)
            this._label.remove_style_class_name('off');
        else
            this._label.add_style_class_name('off');
    }

    refreshStatus() {
        this._updateLabel(daemonRunning());
    }

    _scheduleSave() {
        if (this._saveId)
            GLib.source_remove(this._saveId);
        this._saveId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 150, () => {
            this._saveId = 0;
            try {
                GLib.mkdir_with_parents(CONFIG_DIR, 0o755);
                GLib.file_set_contents(CONFIG_FILE, `${this._factor}\n`);
            } catch (e) {
                logError(e, 'scroll-speed: cannot write config');
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    destroy() {
        if (this._saveId) {
            GLib.source_remove(this._saveId);
            this._saveId = 0;
        }
        super.destroy();
    }
});

const ScrollIndicator = GObject.registerClass(
class ScrollIndicator extends SystemIndicator {
    _init() {
        super._init();
        this.slider = new ScrollSlider();
        this.quickSettingsItems.push(this.slider);
    }
});

export default class ScrollSpeedExtension extends Extension {
    enable() {
        this._indicator = new ScrollIndicator();
        const qs = Main.panel.statusArea.quickSettings;
        qs.addExternalIndicator(this._indicator, 2);
        this._menuId = qs.menu.connect('open-state-changed', (_m, open) => {
            if (open)
                this._indicator.slider.refreshStatus();
        });
    }

    disable() {
        Main.panel.statusArea.quickSettings.menu.disconnect(this._menuId);
        this._indicator.quickSettingsItems.forEach(item => item.destroy());
        this._indicator.destroy();
        this._indicator = null;
    }
}
