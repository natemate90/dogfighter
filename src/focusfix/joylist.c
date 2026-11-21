#define DIRECTINPUT_VERSION 0x0700
#include <windows.h>
#include <dinput.h>
#include <stdio.h>

static IDirectInputA *di;
static int found;

static BOOL has_axis(IDirectInputDevice2A *dev, DWORD offset)
{
    DIDEVICEOBJECTINSTANCEA object = { .dwSize = sizeof(object) };
    return SUCCEEDED(IDirectInputDevice2_GetObjectInfo(dev, &object, offset, DIPH_BYOFFSET));
}

static BOOL CALLBACK on_device(const DIDEVICEINSTANCEA *instance, void *context)
{
    IDirectInputDeviceA *dev1 = NULL;
    IDirectInputDevice2A *dev = NULL;
    DIDEVCAPS caps = { .dwSize = sizeof(caps) };
    const char *throttle = "none";

    found++;
    if (FAILED(IDirectInput_CreateDevice(di, &instance->guidInstance, &dev1, NULL)) ||
        FAILED(IDirectInputDevice_QueryInterface(dev1, &IID_IDirectInputDevice2A, (void **)&dev)) ||
        FAILED(IDirectInputDevice2_SetDataFormat(dev, &c_dfDIJoystick)) ||
        FAILED(IDirectInputDevice2_GetCapabilities(dev, &caps)))
    {
        printf("controller %d: %s (could not be opened)\n", found, instance->tszProductName);
    }
    else
    {
        if (has_axis(dev, DIJOFS_Z)) throttle = "Z";
        else if (has_axis(dev, DIJOFS_SLIDER(0))) throttle = "slider";
        printf("controller %d: %s (%lu axes, %lu buttons, stick %s, throttle axis %s)\n", found,
               instance->tszProductName, caps.dwAxes, caps.dwButtons,
               has_axis(dev, DIJOFS_X) && has_axis(dev, DIJOFS_Y) ? "yes" : "no", throttle);
    }
    if (dev) IDirectInputDevice2_Release(dev);
    if (dev1) IDirectInputDevice_Release(dev1);
    return DIENUM_CONTINUE;
}

int main(void)
{
    HINSTANCE self = GetModuleHandleA(NULL);

    if (FAILED(DirectInputCreateA(self, 0x0700, &di, NULL)) &&
        FAILED(DirectInputCreateA(self, 0x0300, &di, NULL)))
    {
        printf("error: DirectInput did not start\n");
        return 2;
    }
    for (int tries = 0; tries < 25 && !found; tries++)
    {
        if (tries) Sleep(200);
        IDirectInput_EnumDevices(di, DIDEVTYPE_JOYSTICK, on_device, NULL, DIEDFL_ATTACHEDONLY);
    }
    if (!found) printf("no controller found\n");
    IDirectInput_Release(di);
    fflush(stdout);
    return 0;
}
