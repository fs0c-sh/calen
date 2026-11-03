# cal

Personal calendar CLI with server sync.

## Install

```bash
pip3 install git+https://github.com/fs0c-sh/cal.git
```

## Usage

```bash
calendar --help
calendar --sync --host <server> --port <port>
```

`--sync` connects to your calendar server, sends a `HELLO` line, then applies
the event updates the server pushes. On machines that reach the network
through an HTTP proxy, the connection is tunnelled with `CONNECT` using the
standard `http_proxy` / `https_proxy` / `all_proxy` variables. Updates are plain JSON (one event per
line) and are stored under `~/.local/share/cal/`. Nothing pushed is executed.

Events may carry attachments (venue maps, agendas) which are stored under
`~/.local/share/cal/attachments/`.

The relay address above is the staging relay for the migration subnet;
the production VPN does not reach it yet.

## Development

```bash
pip3 install -e .
python3 -m pytest tests/
```

MIT licensed.
