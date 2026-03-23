"""Decode button assignments from exported .dat files."""
import sys
sys.path.insert(0, 'C:/Claude Folder/ROCCAT_Manager')
from SWARM_II_DAT_FORMAT import parse_dat
import struct

HID_KEYS = {
    0x04:'A',0x05:'B',0x06:'C',0x07:'D',0x08:'E',0x09:'F',0x0A:'G',0x0B:'H',
    0x0C:'I',0x0D:'J',0x0E:'K',0x0F:'L',0x10:'M',0x11:'N',0x12:'O',0x13:'P',
    0x14:'Q',0x15:'R',0x16:'S',0x17:'T',0x18:'U',0x19:'V',0x1A:'W',0x1B:'X',
    0x1C:'Y',0x1D:'Z',0x1E:'1',0x1F:'2',0x20:'3',0x21:'4',0x22:'5',0x23:'6',
    0x24:'7',0x25:'8',0x26:'9',0x27:'0',0x28:'Enter',0x29:'Esc',0x2A:'Backspace',
    0x2B:'Tab',0x2C:'Space',0x2D:'-',0x2E:'=',0x2F:'[',0x30:']',0x31:'\\',
    0x33:';',0x34:"'",0x35:'`',0x36:',',0x37:'.',0x38:'/',
    0x3A:'F1',0x3B:'F2',0x3C:'F3',0x3D:'F4',0x3E:'F5',0x3F:'F6',
    0x40:'F7',0x41:'F8',0x42:'F9',0x43:'F10',0x44:'F11',0x45:'F12',
    0x46:'PrintScreen',0x47:'ScrollLock',0x48:'Pause',
    0x49:'Insert',0x4A:'Home',0x4B:'PageUp',0x4C:'Delete',0x4D:'End',0x4E:'PageDown',
    0x4F:'Right',0x50:'Left',0x51:'Down',0x52:'Up',
    0xE0:'LCtrl',0xE1:'LShift',0xE2:'LAlt',0xE3:'LGUI',
    0xE4:'RCtrl',0xE5:'RShift',0xE6:'RAlt',0xE7:'RGUI',
}

MOUSE_ACTIONS = {
    (0x01,0x01):'Left Click',(0x02,0x01):'Right Click',(0x03,0x01):'Middle Click',
    (0x05,0x01):'Browser Forward',(0x06,0x01):'Browser Back',
    (0x07,0x01):'DPI Up',(0x08,0x01):'DPI Down',
    (0x09,0x01):'Scroll Up',(0x0A,0x01):'Scroll Down',
    (0x02,0x02):'Tilt Left',(0x03,0x02):'Tilt Right',
    (0x02,0x03):'Volume Up',(0x03,0x03):'Volume Down',
    (0x04,0x03):'Easy Shift',(0x07,0x03):'DPI Cycle Up',(0x08,0x03):'DPI Cycle Down',
    (0x01,0x08):'DPI Cycle',(0x0B,0x08):'ES DPI',
    (0x01,0x0A):'Profile Cycle',
}

SLOT_NAMES = [
    'Left Click','Right Click','Middle Click','Scroll Up','Scroll Down',
    'Side 1 (Fwd)','Side 2 (Back)','Tilt Left','Tilt Right',
    'Top Front (8)','Top Rear (9)','DPI Up','DPI Down','Profile','Easy Shift'
]

def decode_entry(b0,b1,b2,b3):
    if b0==0 and b1==0 and b2==0 and b3==0:
        return 'Disabled'
    if b3==0x06:
        key = HID_KEYS.get(b1, 'HID_0x%02X' % b1)
        mods = []
        if b2 & 0x01: mods.append('Ctrl')
        if b2 & 0x02: mods.append('Shift')
        if b2 & 0x04: mods.append('Alt')
        if b2 & 0x08: mods.append('Win')
        if mods:
            return '+'.join(mods) + '+' + key
        return key
    action = MOUSE_ACTIONS.get((b2,b3))
    if action:
        return action
    return '%02x %02x %02x %02x' % (b0,b1,b2,b3)

for name in ['Main Test', 'Grounded', 'WWM']:
    path = 'C:/Claude Folder/ROCCAT_Manager/profiles/%s.dat' % name
    parsed = parse_dat(path)

    print('=== %s ===' % name)

    for block in parsed['blocks']:
        if 'dpi_stages' in block:
            print('  DPI stages: %s' % block['dpi_stages'])
        if 'color_rgb' in block:
            print('  Color: #%02x%02x%02x' % block['color_rgb'])

    for block in parsed['blocks']:
        if block['name'] == 'KoneXPAirButtons' and 'button_entries' in block:
            entries = block['button_entries']
            print('  --- Primary ---')
            for i in range(15):
                e = entries[i]
                action = decode_entry(*e)
                print('    %2d %-18s -> %s' % (i, SLOT_NAMES[i], action))
            print('  --- Easy Shift ---')
            for i in range(15, 30):
                e = entries[i]
                action = decode_entry(*e)
                print('    %2d %-18s -> %s' % (i-15, SLOT_NAMES[i-15], action))
    print()
