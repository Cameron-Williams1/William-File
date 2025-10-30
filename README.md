# William Zip Generator

A small but industrial quality utility that continuously creates zip archives, each containing a single text file named `william.txt` with the content `William`. The program is intentionally simple yet it is documented and structured like a professional project so it can serve as a reference for file generation, rate control, lifecycle management, and safe resource handling.

The reference implementation is fewer than ten lines of Python. This README explains how to operate it safely at scale, how to tune performance, and how to deploy it in controlled environments.

---

## Table of Contents

- [Purpose](#purpose)
- [Design Summary](#design-summary)
- [Quick Start](#quick-start)
- [Implementation](#implementation)
- [Operational Guidance](#operational-guidance)
  - [Directory layout](#directory-layout)
  - [Naming scheme](#naming-scheme)
  - [Rate limiting](#rate-limiting)
  - [Retention strategy](#retention-strategy)
  - [Disk space planning](#disk-space-planning)
  - [Signals and termination](#signals-and-termination)
  - [Logging](#logging)
- [Performance](#performance)
  - [Baseline throughput](#baseline-throughput)
  - [I O considerations](#i-o-considerations)
- [Security and Integrity](#security-and-integrity)
- [Cross Platform Notes](#cross-platform-notes)
- [Deployment Options](#deployment-options)
  - [Run under systemd](#run-under-systemd)
  - [Run with Docker](#run-with-docker)
- [Monitoring and Observability](#monitoring-and-observability)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Extending the Tool](#extending-the-tool)
- [FAQ](#faq)

---

## Purpose

Create an ever increasing sequence of zip files for load testing, demo content, and workflow prototyping where a large number of small archives are needed. The tool is intentionally deterministic and side effect free outside the working directory. Each archive contains a single deterministic file with fixed content, which makes verification straightforward.

Typical uses
- Stress testing ingestion pipelines that watch a directory
- Measuring file system performance with small archive creation
- Reproducing scenarios with many small compressed artifacts

This project is not a benchmark of the zip format itself. It is a reproducible generator of small archives that can be controlled with rate and retention strategies.

## Design Summary

- Language: Python, standard library only
- Core library: `zipfile`
- Output: `william_<counter>.zip`
- Contents: `william.txt` with text `William`
- Loop: infinite until interrupted
- State: maintained by an integer counter in memory
- No external network access or dependencies

The choice of a single entry per archive keeps behavior predictable and allows consumers to test unzip operations with minimal CPU overhead.

## Quick Start

Create and activate a dedicated directory and run the program.

```bash
mkdir -p william-out
cd william-out
python3 - <<'PY'
import zipfile, os
i = 0
while True:
    with zipfile.ZipFile(f"william_{i}.zip", "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("william.txt", "William")
    i += 1
PY
```

To stop the program press `Ctrl + C`.

## Implementation

Reference script `william_zipper.py`

```python
import zipfile, os

i = 0
while True:
    with zipfile.ZipFile(f"william_{i}.zip", "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("william.txt", "William")
    i += 1
```

Notes
- `ZIP_DEFLATED` is used for broad compatibility and predictable compression ratios on small files.
- The loop relies on the operating system to flush file handles on context manager exit.
- The counter restarts from zero each process run. If you want to continue numbering from the highest existing index, see the extension recipe in [Extending the Tool](#extending-the-tool).

## Operational Guidance

### Directory layout

Run the program inside a directory dedicated to output. The program writes archives to the current working directory and does not create subdirectories. Example structure after a short run

```
.
├── william_0.zip
├── william_1.zip
├── william_2.zip
└── ...
```

### Naming scheme

Files are named `william_<counter>.zip` with a zero based monotonically increasing counter. The program does not overwrite existing files of the same name. If you restart from zero inside a directory that already contains prior outputs, creation will fail on the first collision. Use an empty folder or enable the resume recipe in the extension section.

### Rate limiting

The reference script does not delay between iterations. On modern hardware this can generate many files per second. If you need to control creation rate, add a sleep

```python
import time
time.sleep(0.1)  # 10 files per second target
```

For more accurate rates, consider token bucket logic or using the operating system scheduler controls like `nice` and `ionice` on Linux.

### Retention strategy

Unbounded generation will eventually consume all available disk space. Suggested strategies
- Cap the number of files by periodically deleting older archives
- Rotate into dated subfolders and prune by age
- Use a dedicated file system or volume with a quota

Example deletion of the oldest 1000 files in a directory on macOS or Linux

```bash
ls -1t william_*.zip | tail -n +1001 | xargs -r rm --
```

### Disk space planning

The content `William` compresses very well. Typical `william.txt` is 7 bytes before compression. With headers and container overhead, each zip is commonly a few hundred bytes. Real sizes depend on the zip implementation and file system block size. Multiply the estimated per file size by the planned file count and add headroom for metadata and journal overhead.

### Signals and termination

- Stop the process with `Ctrl + C`, which sends SIGINT on Unix like systems
- The context manager closes the archive before the exception unwinds, so partially written zips are rare
- For long running services, consider catching `KeyboardInterrupt` to log a clean shutdown

### Logging

The reference script does not log. For traceability, add periodic progress output

```python
if i % 1000 == 0:
    print(f"created {i} files")
```

Redirect stdout to a log file when running unattended.

## Performance

### Baseline throughput

Throughput is usually limited by file system metadata operations rather than compression time, because each archive is very small. On SSD storage, tens of thousands of files per minute is attainable on commodity hardware. Results vary by file system and mount options.

### I O considerations

- Many small files stress directory lookups and inode allocation
- Filesystems with journaling may introduce latency spikes
- Avoid placing the output directory on slow removable media if you target high rates

## Security and Integrity

- Archives are created locally and do not execute code
- The contents are deterministic, which simplifies verification via hashes if desired
- To verify integrity, sample a subset and unzip while comparing the single file content to the expected string

Example verification

```bash
unzip -p william_123.zip william.txt | diff -u - <(printf 'William')
```

## Cross Platform Notes

- Linux, macOS, and Windows with Python 3.6 or newer are supported
- Windows default path length limits may be reached if you embed the output in a deeply nested path. Use shorter directories or enable long paths in Group Policy where appropriate
- On Windows, replace `rm` examples with `del` or use PowerShell equivalents

## Deployment Options

### Run under systemd

Create a service file to manage the process as a background service on Linux systems that use systemd.

`/etc/systemd/system/william-zipper.service`

```
[Unit]
Description=William Zip Generator
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/william-out
ExecStart=/usr/bin/python3 /opt/william/william_zipper.py
Restart=always
RestartSec=2
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7

[Install]
WantedBy=multi-user.target
```

Enable and start

```bash
sudo mkdir -p /opt/william-out
sudo cp william_zipper.py /opt/william/
sudo systemctl enable --now william-zipper.service
```

### Run with Docker

`Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY william_zipper.py /app/william_zipper.py
CMD ["python", "/app/william_zipper.py"]
```

Build and run

```bash
docker build -t william-zipper:latest .
docker run --name william-zipper -v "$PWD/out:/out" -w /out --restart unless-stopped -d william-zipper:latest
```

## Monitoring and Observability

Simple command line checks

```bash
# Count files
ls -1 william_*.zip 2>/dev/null | wc -l

# Monitor growth in real time
watch -n 1 'ls -1 | wc -l; du -sh .'
```

File system watchers can be used to trigger downstream workflows as files arrive. On Linux consider `inotifywait`. On macOS consider `fs_events` or `fswatch`.

## Testing

Unit test example that validates one archive creation

```python
import zipfile, os, tempfile, subprocess, sys

def test_single_creation():
    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, "s.py")
        with open(script, "w") as f:
            f.write("import zipfile
with zipfile.ZipFile('william_0.zip','w') as z:z.writestr('william.txt','William')")
        subprocess.check_call([sys.executable, script], cwd=tmp)
        assert os.path.exists(os.path.join(tmp, "william_0.zip"))
        with zipfile.ZipFile(os.path.join(tmp, "william_0.zip")) as z:
            assert z.read("william.txt").decode() == "William"
```

## Troubleshooting

- Permission denied
  - Ensure write permission to the working directory
- Disk full
  - Free space or prune older files
- Slow creation rate
  - Reduce logging, avoid network file systems, and verify the device is not heavily loaded
- File name collisions after a restart
  - Use an empty directory or enable the resume recipe below

## Extending the Tool

Resume from the highest existing index

```python
import zipfile, os, re

def next_index(prefix='william_', suffix='.zip'):
    r = re.compile(rf"^{re.escape(prefix)}(\d+){re.escape(suffix)}$")
    existing = [int(m.group(1)) for m in map(r.match, os.listdir()) if m]
    return max(existing) + 1 if existing else 0

i = next_index()
while True:
    with zipfile.ZipFile(f"william_{i}.zip","w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("william.txt","William")
    i += 1
```

Throttle by maximum size of the output directory

```python
import os, shutil, zipfile, time

MAX_BYTES = 500 * 1024 * 1024  # 500 MiB

def dir_size(path='.'):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
            except FileNotFoundError:
                pass
    return total

i = 0
while True:
    while dir_size('.') > MAX_BYTES:
        time.sleep(0.5)
    with zipfile.ZipFile(f"william_{i}.zip","w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("william.txt","William")
    i += 1
```

## FAQ

- Why is each archive so small
  - The payload is the seven character string `William`. The archive container adds headers and a central directory which dominate the size
- Can I store a different string
  - Yes. Replace the content passed to `writestr`
- Can I place the output into subdirectories by date or hour
  - Yes. Create directories with `os.makedirs` and write into those paths before each iteration
- Can I parallelize creation
  - It is possible but not necessary for most use cases. Parallel creators must coordinate index assignment to avoid collisions. Consider per process prefixes or a shared counter file

This project keeps the code small while providing production grade guidance for safe and predictable operation.
