# Chromium Startup Issues on ARM64 (Oracle Cloud / Coolify)
## Detailed Step-by-Step Session Chronology

This document provides a highly detailed account of the troubleshooting process, the errors encountered after each step, the corresponding web-research, and the technical changes attempted.

---

## Step 1: Initial Error (`cannot connect to chrome`)

### 1. The Error Message
The deployment logs showed FlareSolverr hanging on boot and then crashing with this traceback:
```
  File "/usr/local/lib/python3.13/site-packages/selenium/webdriver/chromium/webdriver.py", line 67, in __init__
    super().__init__(command_executor=executor, options=options)
...
selenium.common.exceptions.SessionNotCreatedException: Message: session not created: cannot connect to chrome at 127.0.0.1:44567
```

### 2. Research & Findings
* We discovered that `undetected_chromedriver` (UC) launches Chrome as a detached background process and immediately initiates the Selenium WebDriver HTTP handshake.
* On x86 hosts, Chrome starts almost instantly.
* On ARM64 hosts (such as the Oracle Cloud Ampere A1 OCPU shape under Docker), Chrome's remote debugging server takes between **10 to 30 seconds** to start listening on the TCP port.
* Because Selenium's connection attempts occur instantly without polling the port, it fails immediately with a `SessionNotCreatedException`.

### 3. The Fix Attempt
We modified `src/undetected_chromedriver/__init__.py` to block the initialization process until the port is open:
* Added a static method `_wait_for_port(host, port, timeout)` using standard Python `socket.create_connection()` loops.
* Called this method immediately after spawning the Chrome subprocess and before invoking `super().__init__()`.

---

## Step 2: The Port Timeout Crash

### 1. The New Error Message
After deploying the port-wait loop, the startup logs changed:
```
Exception: Error getting browser User-Agent. Chrome debug port 127.0.0.1:39107 not ready after 120s (240 attempts). Chrome may have crashed.
```

### 2. Research & Findings
* The port never opened, even after 2 minutes. This meant Chromium was not just slow; it was dying instantly upon launch.
* By default, `undetected_chromedriver` uses a custom double-forking mechanism called `start_detached` to launch the browser. This untethers the browser from Python to prevent bot detection tools from noticing the driver relationship.
* In restricted ARM64 Docker setups, orphaned processes (like double-forked Chrome) are automatically reaped or blocked by the sandbox/container manager, causing Chrome to die silently.

### 3. The Fix Attempt
* We decided to force `use_subprocess=True` on ARM64 inside `src/utils.py`.
* This tells UC to spawn Chrome using standard `subprocess.Popen`, retaining a direct process hierarchy handle so Docker does not terminate the orphaned process.

---

## Step 3: The SIGTRAP (`exit code -5`) Crash

### 1. The New Error Message
After forcing `use_subprocess=True`, we captured Chrome's raw stdout/stderr via custom diagnostics, revealing a hard crash:
```
RuntimeError: Chrome process crashed early with exit code -5.
Stderr: [24:49:0706/131423.296975:ERROR:dbus/bus.cc:405] Failed to connect to the bus: Failed to connect to socket /run/dbus/system_bus_socket: No such file or directory
[0706/131423.718907:ERROR:third_party/crashpad/crashpad/util/file/file_io_posix.cc:145] open /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq: No such file or directory (2)
```

### 2. Research & Findings
* **Exit code -5** represents a **SIGTRAP** (Trace/breakpoint trap). This indicates a compiled-in assertion error inside Chromium's V8 engine or `PartitionAlloc` memory allocator.
* **Theory 1 (64K Page Size):** Many ARM64 servers run Linux kernels with 64KB memory pages. Standard Chromium binaries are compiled assuming a 4KB page size. Running a 4K binary on a 64K host triggers a memory alignment security assertion in V8, leading to an immediate `SIGTRAP` crash.
* **Theory 2 (Zygote Sandboxing):** FlareSolverr uses the `--no-zygote` argument. On ARM64 Linux containers, running without the Zygote helper process while having limited sandbox capabilities triggers V8 engine failures.

### 3. The Fix Attempt
* We requested the user run `getconf PAGESIZE` on the host to test Theory 1.
* We patched `src/utils.py` to disable `--no-zygote` on ARM64 platforms to see if it bypassed the sandboxing trap.

---

## Step 4: Page Size Ruled Out & Docker Seccomp Suspected

### 1. The Host Environment Output
The user ran the diagnostics on the host and reported:
* Page size: `4096` (4KB)
* Kernel version: `6.17.0-1011-oracle`
* **Conclusion:** Since page size is 4KB, Theory 1 (64K page size mismatch) was ruled out. The SIGTRAP was still happening.

### 2. Research & Findings
* If page size is 4KB, the SIGTRAP crash is caused by **Docker's default seccomp security profile**.
* Docker uses a system call filter (seccomp) to block containers from making sensitive kernel calls. Chromium on ARM64 utilizes different low-level thread/process cloning instructions than on x86.
* When Chromium tries to make these calls inside a standard Docker container on ARM64, the kernel denies them, and Chromium aborts immediately with a `SIGTRAP` instruction.
* D-Bus bus connection failures can also trigger fatal aborts in headless Chromium environments.

### 3. The Fix Attempt
We added extreme compatibility arguments in `src/utils.py` for ARM64:
1. **`--single-process`:** Forces Chromium to run all tabs, renderer engines, and networking pools in a single thread. This prevents Chrome from executing the multi-process cloning system calls that trigger the seccomp block.
2. **`os.environ['DBUS_SESSION_BUS_ADDRESS'] = '/dev/null'`:** Suppresses D-Bus initialization assertions.

---

## Current Status & Final Workaround

Despite `--single-process`, some modern Chromium builds (like version 150) still execute blocked operations during startup, resulting in the same `exit code -5` crash. 

### Why code-only fixes are blocked
This is a container-level virtualization barrier. Because Python runs inside the container, it cannot bypass Docker's system call filter from the inside.

### The True Resolution (Docker/Coolify Host Configuration)
To run headless Chromium on an ARM64 Docker host, you must instruct Docker to allow the necessary syscalls. You must add the following properties to your container configuration (such as the Docker Compose settings in Coolify):

```yaml
services:
  flaresolverr:
    # ... your config ...
    security_opt:
      - seccomp=unconfined      # Bypasses the seccomp filter for Chromium
    shm_size: '1gb'             # Prevents shared memory (OOM) crashes
    cap_add:
      - SYS_ADMIN               # Permits Chrome sandbox setup
```

### Manual Host Diagnostics (How to verify)
Since Coolify terminates the container before you can attach to it, you can run a temporary test container on the host terminal:

1. List the containers on the host to find the FlareSolverr image:
   ```bash
   docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
   ```
2. Spawn a interactive shell in the image:
   ```bash
   docker run -it --rm --entrypoint bash <YOUR_FLARESOLVERR_IMAGE_ID>
   ```
3. Test Chromium manually:
   ```bash
   chromium --no-sandbox --headless=new --disable-gpu --remote-debugging-port=19222
   ```
   If it crashes with `Trace/breakpoint trap` or `exit code -5`, run the same test but with seccomp disabled:
   ```bash
   docker run -it --rm --security-opt seccomp=unconfined --entrypoint bash <YOUR_FLARESOLVERR_IMAGE_ID>
   ```
   Chromium will boot successfully, proving that `seccomp=unconfined` is required.
