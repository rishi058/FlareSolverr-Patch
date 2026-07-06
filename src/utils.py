import json
import logging
import os
import platform
import re
import shutil
import sys
import tempfile
import urllib.parse

from selenium.webdriver.chrome.webdriver import WebDriver
import undetected_chromedriver as uc

FLARESOLVERR_VERSION = None
PLATFORM_VERSION = None
CHROME_EXE_PATH = None
CHROME_MAJOR_VERSION = None
USER_AGENT = None
XVFB_DISPLAY = None
PATCHED_DRIVER_PATH = None


def get_config_log_html() -> bool:
    return os.environ.get('LOG_HTML', 'false').lower() == 'true'


def get_config_headless() -> bool:
    return os.environ.get('HEADLESS', 'true').lower() == 'true'


def get_config_disable_media() -> bool:
    return os.environ.get('DISABLE_MEDIA', 'false').lower() == 'true'


def get_flaresolverr_version() -> str:
    global FLARESOLVERR_VERSION
    if FLARESOLVERR_VERSION is not None:
        return FLARESOLVERR_VERSION

    package_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'package.json')
    if not os.path.isfile(package_path):
        package_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'package.json')
    with open(package_path) as f:
        FLARESOLVERR_VERSION = json.loads(f.read())['version']
        return FLARESOLVERR_VERSION

def get_current_platform() -> str:
    global PLATFORM_VERSION
    if PLATFORM_VERSION is not None:
        return PLATFORM_VERSION
    PLATFORM_VERSION = os.name
    return PLATFORM_VERSION


def create_proxy_extension(proxy: dict) -> str:
    parsed_url = urllib.parse.urlparse(proxy['url'])
    scheme = parsed_url.scheme
    host = parsed_url.hostname
    port = parsed_url.port
    username = proxy['username']
    password = proxy['password']
    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 3,
        "name": "Chrome Proxy",
        "permissions": [
            "proxy",
            "tabs",
            "storage",
            "webRequest",
            "webRequestAuthProvider"
        ],
        "host_permissions": [
          "<all_urls>"
        ],
        "background": {
          "service_worker": "background.js"
        },
        "minimum_chrome_version": "76.0.0"
    }
    """

    background_js = """
    var config = {
        mode: "fixed_servers",
        rules: {
            singleProxy: {
                scheme: "%s",
                host: "%s",
                port: %d
            },
            bypassList: ["localhost"]
        }
    };

    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});

    function callbackFn(details) {
        return {
            authCredentials: {
                username: "%s",
                password: "%s"
            }
        };
    }

    chrome.webRequest.onAuthRequired.addListener(
        callbackFn,
        { urls: ["<all_urls>"] },
        ['blocking']
    );
    """ % (
        scheme,
        host,
        port,
        username,
        password
    )

    proxy_extension_dir = tempfile.mkdtemp()

    with open(os.path.join(proxy_extension_dir, "manifest.json"), "w") as f:
        f.write(manifest_json)

    with open(os.path.join(proxy_extension_dir, "background.js"), "w") as f:
        f.write(background_js)

    return proxy_extension_dir


def get_webdriver(proxy: dict = None) -> WebDriver:
    global PATCHED_DRIVER_PATH, USER_AGENT
    logging.debug('Launching web browser...')

    # undetected_chromedriver
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-search-engine-choice-screen')
    # todo: this param shows a warning in chrome head-full
    options.add_argument('--disable-setuid-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    IS_ARMARCH = platform.machine().startswith(('arm', 'aarch'))
    logging.info("[utils] platform.machine()=%s IS_ARMARCH=%s", platform.machine(), IS_ARMARCH)
    if not IS_ARMARCH:
        # this option removes the zygote sandbox (it seems that the resolution is a bit faster)
        # However, it causes SIGTRAP (exit code -5) crashes on ARM64 Docker.
        options.add_argument('--no-zygote')
        logging.debug("[utils] Added --no-zygote (x86 only)")
    
    # attempt to fix Docker ARM32/ARM64 build
    if IS_ARMARCH:
        options.add_argument('--disable-gpu-sandbox')
        options.add_argument('--disable-gpu')          # no GPU/DRM on Oracle Cloud ARM VMs
        options.add_argument('--disable-software-rasterizer')
        # options.add_argument('--single-process')     # CAUSES SIGTRAP on Chromium 150!
        os.environ['DBUS_SESSION_BUS_ADDRESS'] = '/dev/null' # suppress DBus fatal traps
        logging.info("[utils] ARM flags added: disable-gpu-sandbox, disable-gpu, disable-software-rasterizer, DBUS=/dev/null")

    options.add_argument('--ignore-certificate-errors')
    options.add_argument('--ignore-ssl-errors')

    language = os.environ.get('LANG', None)
    if language is not None:
        options.add_argument('--accept-lang=%s' % language)

    # Fix for Chrome 117 | https://github.com/FlareSolverr/FlareSolverr/issues/910
    if USER_AGENT is not None:
        options.add_argument('--user-agent=%s' % USER_AGENT)

    proxy_extension_dir = None
    if proxy and all(key in proxy for key in ['url', 'username', 'password']):
        proxy_extension_dir = create_proxy_extension(proxy)
        options.add_argument("--disable-features=DisableLoadExtensionCommandLineSwitch")
        options.add_argument("--load-extension=%s" % os.path.abspath(proxy_extension_dir))
    elif proxy and 'url' in proxy:
        proxy_url = proxy['url']
        logging.debug("Using webdriver proxy: %s", proxy_url)
        options.add_argument('--proxy-server=%s' % proxy_url)

    # Headless strategy:
    # - Windows: use UC's windows_headless mode
    # - ARM Linux (Oracle Cloud etc.): use --headless=new via UC's headless param.
    #   use_subprocess=True avoids start_detached (double-fork) which crashes on ARM.
    #   Port-readiness wait in UC handles the slow Chrome startup.
    # - x86 Linux: use Xvfb (head-full behind virtual display, less detectable)
    #   Falls back to --headless=new if Xvfb fails.
    windows_headless = False
    headless_flag = False
    use_subprocess = False
    if get_config_headless():
        if os.name == 'nt':
            windows_headless = True
            logging.info("[utils] Headless mode: windows_headless")
        elif IS_ARMARCH:
            # ARM: skip Xvfb, use subprocess mode (start_detached crashes on ARM)
            logging.info('[utils] ARM detected — using headless=True + use_subprocess=True + port-wait')
            headless_flag = True
            use_subprocess = True
        else:
            xvfb_ok = start_xvfb_display()
            if not xvfb_ok:
                # Native headless fallback — works without any display server
                logging.info("[utils] Xvfb unavailable — falling back to --headless=new")
                headless_flag = True
    
    # if we are inside the Docker container, we avoid downloading the driver
    driver_exe_path = None
    version_main = None
    if os.path.exists("/app/chromedriver"):
        # running inside Docker
        driver_exe_path = "/app/chromedriver"
        logging.info("[utils] Docker mode: using pre-installed chromedriver at %s", driver_exe_path)
    else:
        version_main = get_chrome_major_version()
        logging.info("[utils] Non-Docker mode: Chrome major version=%s", version_main)
        if PATCHED_DRIVER_PATH is not None:
            driver_exe_path = PATCHED_DRIVER_PATH
            logging.info("[utils] Reusing cached patched driver at %s", driver_exe_path)

    # detect chrome path
    browser_executable_path = get_chrome_exe_path()
    logging.info("[utils] Browser executable: %s", browser_executable_path)

    # downloads and patches the chromedriver
    # if we don't set driver_executable_path it downloads, patches, and deletes the driver each time
    logging.info(
        "[utils] uc.Chrome() call — browser=%s driver=%s version_main=%s "
        "windows_headless=%s headless=%s use_subprocess=%s",
        browser_executable_path, driver_exe_path, version_main,
        windows_headless, headless_flag, use_subprocess
    )
    try:
        driver = uc.Chrome(options=options, browser_executable_path=browser_executable_path,
                           driver_executable_path=driver_exe_path, version_main=version_main,
                           windows_headless=windows_headless, headless=headless_flag,
                           use_subprocess=use_subprocess)
    except Exception as e:
        logging.error("[utils] Error starting Chrome: %s", e)
        # No point in continuing if we cannot retrieve the driver
        raise e

    # save the patched driver to avoid re-downloads
    if driver_exe_path is None:
        PATCHED_DRIVER_PATH = os.path.join(driver.patcher.data_path, driver.patcher.exe_name)
        if PATCHED_DRIVER_PATH != driver.patcher.executable_path:
            shutil.copy(driver.patcher.executable_path, PATCHED_DRIVER_PATH)
            logging.debug("[utils] Cached patched driver to %s", PATCHED_DRIVER_PATH)

    logging.info("[utils] WebDriver launched successfully")

    # clean up proxy extension directory
    if proxy_extension_dir is not None:
        shutil.rmtree(proxy_extension_dir)

    return driver


def get_chrome_exe_path() -> str:
    global CHROME_EXE_PATH
    if CHROME_EXE_PATH is not None:
        return CHROME_EXE_PATH
    # linux pyinstaller bundle
    chrome_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chrome', "chrome")
    if os.path.exists(chrome_path):
        if not os.access(chrome_path, os.X_OK):
            raise Exception(f'Chrome binary "{chrome_path}" is not executable. '
                            f'Please, extract the archive with "tar xzf <file.tar.gz>".')
        CHROME_EXE_PATH = chrome_path
        logging.info("[utils] Chrome found (linux pyinstaller bundle): %s", CHROME_EXE_PATH)
        return CHROME_EXE_PATH
    # windows pyinstaller bundle
    chrome_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chrome', "chrome.exe")
    if os.path.exists(chrome_path):
        CHROME_EXE_PATH = chrome_path
        logging.info("[utils] Chrome found (windows pyinstaller bundle): %s", CHROME_EXE_PATH)
        return CHROME_EXE_PATH
    # ARM Linux: Debian/Ubuntu package manager installs Chromium as
    # /usr/bin/chromium (or /usr/bin/chromium-browser). These paths are
    # not in uc.find_chrome_executable()'s search list, which looks for
    # google-chrome / google-chrome-stable instead.
    # Check these before delegating to UC so ARM Docker containers
    # always find the correct native binary.
    for _candidate in ("/usr/bin/chromium", "/usr/bin/chromium-browser"):
        if os.path.exists(_candidate):
            CHROME_EXE_PATH = _candidate
            logging.info("[utils] Chrome found (ARM distro candidate): %s", CHROME_EXE_PATH)
            return CHROME_EXE_PATH
    # system (searches for google-chrome, chromium, etc.)
    CHROME_EXE_PATH = uc.find_chrome_executable()
    logging.info("[utils] Chrome found (uc.find_chrome_executable): %s", CHROME_EXE_PATH)
    return CHROME_EXE_PATH


def get_chrome_major_version() -> str:
    global CHROME_MAJOR_VERSION
    if CHROME_MAJOR_VERSION is not None:
        return CHROME_MAJOR_VERSION

    if os.name == 'nt':
        # Example: '104.0.5112.79'
        try:
            complete_version = extract_version_nt_executable(get_chrome_exe_path())
        except Exception:
            try:
                complete_version = extract_version_nt_registry()
            except Exception:
                # Example: '104.0.5112.79'
                complete_version = extract_version_nt_folder()
    else:
        chrome_path = get_chrome_exe_path()
        process = os.popen(f'"{chrome_path}" --version')
        # Example 1: 'Chromium 104.0.5112.79 Arch Linux\n'
        # Example 2: 'Google Chrome 104.0.5112.79 Arch Linux\n'
        complete_version = process.read()
        process.close()

    CHROME_MAJOR_VERSION = complete_version.split('.')[0].split(' ')[-1]
    return CHROME_MAJOR_VERSION


def extract_version_nt_executable(exe_path: str) -> str:
    import pefile
    pe = pefile.PE(exe_path, fast_load=True)
    pe.parse_data_directories(
        directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]]
    )
    return pe.FileInfo[0][0].StringTable[0].entries[b"FileVersion"].decode('utf-8')


def extract_version_nt_registry() -> str:
    stream = os.popen(
        'reg query "HKLM\\SOFTWARE\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Google Chrome"')
    output = stream.read()
    google_version = ''
    for letter in output[output.rindex('DisplayVersion    REG_SZ') + 24:]:
        if letter != '\n':
            google_version += letter
        else:
            break
    return google_version.strip()


def extract_version_nt_folder() -> str:
    # Check if the Chrome folder exists in the x32 or x64 Program Files folders.
    for i in range(2):
        path = 'C:\\Program Files' + (' (x86)' if i else '') + '\\Google\\Chrome\\Application'
        if os.path.isdir(path):
            paths = [f.path for f in os.scandir(path) if f.is_dir()]
            for path in paths:
                filename = os.path.basename(path)
                pattern = r'\d+\.\d+\.\d+\.\d+'
                match = re.search(pattern, filename)
                if match and match.group():
                    # Found a Chrome version.
                    return match.group(0)
    return ''


def get_user_agent(driver=None) -> str:
    global USER_AGENT
    if USER_AGENT is not None:
        return USER_AGENT

    try:
        if driver is None:
            driver = get_webdriver()
        USER_AGENT = driver.execute_script("return navigator.userAgent")
        # Fix for Chrome 117 | https://github.com/FlareSolverr/FlareSolverr/issues/910
        USER_AGENT = re.sub('HEADLESS', '', USER_AGENT, flags=re.IGNORECASE)
        return USER_AGENT
    except Exception as e:
        raise Exception("Error getting browser User-Agent. " + str(e))
    finally:
        if driver is not None:
            if PLATFORM_VERSION == "nt":
                driver.close()
            driver.quit()


def start_xvfb_display() -> bool:
    """
    Start a virtual X display (Xvfb) for headless Chrome.
    Returns True if Xvfb started and produced a usable DISPLAY,
    False if it failed (caller should fall back to --headless=new).
    """
    global XVFB_DISPLAY
    if XVFB_DISPLAY is not None:
        return True
    try:
        from xvfbwrapper import Xvfb
        logging.info("[utils] Starting Xvfb virtual display...")
        XVFB_DISPLAY = Xvfb()
        XVFB_DISPLAY.start()
        # Verify that a real DISPLAY was registered (fails silently on some ARM VMs)
        if not os.environ.get('DISPLAY'):
            raise RuntimeError('Xvfb started but DISPLAY env var is not set')
        logging.info("[utils] Xvfb started, DISPLAY=%s", os.environ.get('DISPLAY'))
        return True
    except Exception as e:
        logging.warning(f'[utils] Xvfb failed to start ({e}); falling back to --headless=new')
        XVFB_DISPLAY = None
        return False


def object_to_dict(_object):
    json_dict = json.loads(json.dumps(_object, default=lambda o: o.__dict__))
    # remove hidden fields
    return {k: v for k, v in json_dict.items() if not k.startswith('__')}
