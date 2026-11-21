#define WIN32_LEAN_AND_MEAN
#define CINTERFACE
#define COBJMACROS
#include <windows.h>
#include <d3d9.h>
#include <cwchar>

using Create9 = IDirect3D9 *(WINAPI *)(UINT);
using CreateDevice = decltype(IDirect3D9Vtbl::CreateDevice);
using Reset = decltype(IDirect3DDevice9Vtbl::Reset);

static CreateDevice original_create_device;
static Reset original_reset;

template <typename Method>
static bool set_hook(Method *slot, Method replacement, Method *original) {
    if (*slot == replacement) return true;
    if (*original && *slot != *original) return false;

    DWORD previous;
    if (!VirtualProtect(slot, sizeof(*slot), PAGE_READWRITE, &previous)) return false;
    *original = *slot;
    *slot = replacement;
    DWORD ignored;
    VirtualProtect(slot, sizeof(*slot), previous, &ignored);
    return true;
}

static D3DPRESENT_PARAMETERS as_windowed(const D3DPRESENT_PARAMETERS &params) {
    D3DPRESENT_PARAMETERS copy = params;
    copy.Windowed = TRUE;
    copy.FullScreen_RefreshRateInHz = 0;
    copy.BackBufferFormat = D3DFMT_UNKNOWN;
    return copy;
}

static void frame_game_window(HWND window, UINT width, UINT height) {
    if (!window) return;
    window = GetAncestor(window, GA_ROOT);
    DWORD owner = 0;
    GetWindowThreadProcessId(window, &owner);
    if (owner != GetCurrentProcessId()) return;

    MONITORINFO monitor{};
    monitor.cbSize = sizeof(monitor);
    if (!GetMonitorInfoW(MonitorFromWindow(window, MONITOR_DEFAULTTOPRIMARY), &monitor)) return;
    const RECT &work = monitor.rcWork;
    const auto style = static_cast<DWORD>(GetWindowLongPtrW(window, GWL_STYLE));
    const auto ex_style = static_cast<DWORD>(GetWindowLongPtrW(window, GWL_EXSTYLE));
    const DWORD frame_style = (style & ~WS_POPUP) | WS_OVERLAPPEDWINDOW;
    RECT current{};
    if (style == frame_style && !(ex_style & WS_EX_TOPMOST) && GetWindowRect(window, &current)
        && current.left >= work.left && current.top >= work.top
        && current.right <= work.right && current.bottom <= work.bottom) return;

    RECT border{};
    if (!AdjustWindowRectEx(&border, frame_style, GetMenu(window) != nullptr, ex_style)) return;
    const LONG frame_width = border.right - border.left;
    const LONG frame_height = border.bottom - border.top;
    const LONG max_width = work.right - work.left - frame_width;
    const LONG max_height = work.bottom - work.top - frame_height;
    if (max_width <= 0 || max_height <= 0) return;

    LONG client_width = width && width <= 8192 ? static_cast<LONG>(width) : 800;
    LONG client_height = height && height <= 8192 ? static_cast<LONG>(height) : 600;
    if (client_width > max_width) {
        client_height = MulDiv(client_height, max_width, client_width);
        client_width = max_width;
    }
    if (client_height > max_height) {
        client_width = MulDiv(client_width, max_height, client_height);
        client_height = max_height;
    }
    const LONG window_width = (client_width > 0 ? client_width : 1) + frame_width;
    const LONG window_height = (client_height > 0 ? client_height : 1) + frame_height;
    SetWindowLongPtrW(window, GWL_STYLE, frame_style);
    SetWindowPos(window, HWND_NOTOPMOST, work.left + (work.right - work.left - window_width) / 2,
        work.top + (work.bottom - work.top - window_height) / 2, window_width, window_height,
        SWP_FRAMECHANGED | SWP_NOACTIVATE | SWP_NOOWNERZORDER);
}

static HRESULT STDMETHODCALLTYPE hook_reset(IDirect3DDevice9 *device, D3DPRESENT_PARAMETERS *params) {
    if (!params) return D3DERR_INVALIDCALL;
    auto converted = as_windowed(*params);
    const HRESULT result = original_reset(device, &converted);
    if (SUCCEEDED(result)) {
        D3DDEVICE_CREATION_PARAMETERS creation{};
        IDirect3DDevice9_GetCreationParameters(device, &creation);
        frame_game_window(converted.hDeviceWindow ? converted.hDeviceWindow : creation.hFocusWindow,
            converted.BackBufferWidth, converted.BackBufferHeight);
    }
    return result;
}

static HRESULT STDMETHODCALLTYPE hook_create_device(IDirect3D9 *d3d, UINT adapter, D3DDEVTYPE type,
    HWND window, DWORD behavior, D3DPRESENT_PARAMETERS *params, IDirect3DDevice9 **device) {
    if (!params || !device) return D3DERR_INVALIDCALL;
    auto converted = as_windowed(*params);
    const HRESULT result = original_create_device(d3d, adapter, type, window, behavior, &converted, device);
    if (FAILED(result)) return result;
    if (!*device) return D3DERR_NOTAVAILABLE;
    if (!set_hook(&(*device)->lpVtbl->Reset, hook_reset, &original_reset)) {
        IDirect3DDevice9_Release(*device);
        *device = nullptr;
        return D3DERR_NOTAVAILABLE;
    }
    frame_game_window(converted.hDeviceWindow ? converted.hDeviceWindow : window,
        converted.BackBufferWidth, converted.BackBufferHeight);
    return result;
}

static Create9 load_system_create9() {
    wchar_t path[MAX_PATH];
    const UINT length = GetSystemDirectoryW(path, ARRAYSIZE(path));
    if (!length || length >= ARRAYSIZE(path) || wcscat_s(path, L"\\d3d9.dll") != 0) return nullptr;
    const HMODULE runtime = LoadLibraryExW(path, nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!runtime) return nullptr;
    return reinterpret_cast<Create9>(GetProcAddress(runtime, "Direct3DCreate9"));
}

extern "C" IDirect3D9 *WINAPI WindowedDirect3DCreate9(UINT sdk_version) {
    static const Create9 system_create9 = load_system_create9();
    if (!system_create9 || system_create9 == WindowedDirect3DCreate9) return nullptr;

    IDirect3D9 *d3d = system_create9(sdk_version);
    if (d3d && !set_hook(&d3d->lpVtbl->CreateDevice, hook_create_device, &original_create_device)) {
        IDirect3D9_Release(d3d);
        return nullptr;
    }
    return d3d;
}
