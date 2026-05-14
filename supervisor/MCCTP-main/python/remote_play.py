"""Remote play - control Minecraft from another computer using pygame."""

import argparse
import sys
import threading

import pygame

from mcctp import SyncMCCTPClient, Actions

DEFAULT_PORT = 8765
MOUSE_SENSITIVITY = 0.15
FPS = 30
WIN_W, WIN_H = 640, 360


def ask_host_dialog() -> str | None:
    """Show a tkinter dialog to ask for the host IP. Returns the IP or None if cancelled."""
    import tkinter as tk

    result: list[str | None] = [None]

    root = tk.Tk()
    root.title("MCCTP Remote Play")
    root.resizable(False, False)

    tk.Label(root, text="Host IP:", font=("Arial", 12)).pack(padx=10, pady=(10, 0))
    entry = tk.Entry(root, font=("Arial", 12), width=25)
    entry.insert(0, "localhost")
    entry.pack(padx=10, pady=5)
    entry.select_range(0, tk.END)
    entry.focus_set()

    def on_connect():
        result[0] = entry.get().strip() or "localhost"
        root.destroy()

    def on_enter(event):
        on_connect()

    entry.bind("<Return>", on_enter)
    tk.Button(root, text="Connect", font=("Arial", 11), command=on_connect).pack(pady=(0, 10))

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    return result[0]


def main():
    parser = argparse.ArgumentParser(description="Remote play - control Minecraft via MCCTP")
    parser.add_argument("--host", default=None, help="Target IP address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Target port (default: {DEFAULT_PORT})")
    args = parser.parse_args()

    host = args.host
    if host is None:
        host = ask_host_dialog()
        if host is None:
            print("No host specified, exiting.")
            sys.exit(0)

    # -- Connect MCCTP --
    state_data: dict = {}
    state_lock = threading.Lock()
    connected = True

    def on_state(state):
        with state_lock:
            state_data.update(state)

    client = SyncMCCTPClient(host, args.port)
    client.on_state(on_state)
    try:
        client.connect()
    except Exception as e:
        print(f"Failed to connect to {host}:{args.port} - {e}")
        sys.exit(1)

    # -- Pygame init --
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption(f"MCCTP Remote Play - {host}")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 16)

    held_keys: set[str] = set()
    mouse_grabbed = False
    running = True

    key_map = {
        pygame.K_w: ("move", "forward"),
        pygame.K_s: ("move", "backward"),
        pygame.K_a: ("move", "left"),
        pygame.K_d: ("move", "right"),
    }

    def send(action):
        nonlocal connected
        try:
            client.send(action)
        except Exception:
            connected = False

    def set_grab(grab: bool):
        nonlocal mouse_grabbed
        mouse_grabbed = grab
        pygame.event.set_grab(grab)
        pygame.mouse.set_visible(not grab)
        if grab:
            pygame.mouse.get_rel()  # flush accumulated delta

    def release_all():
        for k in list(held_keys):
            if k in ("forward", "backward", "left", "right"):
                send(Actions.move(k, "stop"))
            elif k == "sneak":
                send(Actions.sneak("stop"))
            elif k == "sprint":
                send(Actions.sprint("stop"))
            elif k == "use_item":
                send(Actions.use_item("stop"))
        held_keys.clear()

    # -- Main loop --
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break

            elif event.type == pygame.KEYDOWN:
                key = event.key

                if key == pygame.K_ESCAPE:
                    if mouse_grabbed:
                        set_grab(False)
                    else:
                        running = False
                    continue

                if key == pygame.K_F1:
                    set_grab(not mouse_grabbed)
                    continue

                if key == pygame.K_SPACE:
                    send(Actions.jump())
                    continue

                if key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
                    if "sneak" not in held_keys:
                        held_keys.add("sneak")
                        send(Actions.sneak("start"))
                    continue

                if key in (pygame.K_LCTRL, pygame.K_RCTRL):
                    if "sprint" not in held_keys:
                        held_keys.add("sprint")
                        send(Actions.sprint("start"))
                    continue

                if key in key_map:
                    _, direction = key_map[key]
                    if direction not in held_keys:
                        held_keys.add(direction)
                        send(Actions.move(direction, "start"))
                    continue

                if pygame.K_1 <= key <= pygame.K_9:
                    send(Actions.select_slot(key - pygame.K_1))
                    continue

                if key == pygame.K_q:
                    send(Actions.drop_item(full_stack=False))
                elif key == pygame.K_e:
                    send(Actions.open_inventory())
                elif key == pygame.K_f:
                    send(Actions.swap_hands())
                elif key == pygame.K_v:
                    send(Actions.toggle_wheel())

            elif event.type == pygame.KEYUP:
                key = event.key

                if key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
                    if "sneak" in held_keys:
                        held_keys.discard("sneak")
                        send(Actions.sneak("stop"))
                    continue

                if key in (pygame.K_LCTRL, pygame.K_RCTRL):
                    if "sprint" in held_keys:
                        held_keys.discard("sprint")
                        send(Actions.sprint("stop"))
                    continue

                if key in key_map:
                    _, direction = key_map[key]
                    if direction in held_keys:
                        held_keys.discard(direction)
                        send(Actions.move(direction, "stop"))

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    send(Actions.attack())
                elif event.button == 3:
                    if "use_item" not in held_keys:
                        held_keys.add("use_item")
                        send(Actions.use_item("start"))

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 3:
                    if "use_item" in held_keys:
                        held_keys.discard("use_item")
                        send(Actions.use_item("stop"))

        # Mouse look
        if mouse_grabbed:
            dx, dy = pygame.mouse.get_rel()
            if abs(dx) > 0 or abs(dy) > 0:
                send(Actions.look(
                    yaw=dx * MOUSE_SENSITIVITY,
                    pitch=dy * MOUSE_SENSITIVITY,
                    relative=True,
                ))

        # -- Render HUD --
        screen.fill((20, 20, 30))

        with state_lock:
            ps = state_data.get("playerState", {})
            hi = state_data.get("heldItem", {})

        lines = [
            f"MCCTP Remote Play",
            f"",
            f"Connection: {'OK' if connected else 'LOST'}",
            f"Mouse Lock: {'ON  (F1 toggle, ESC release)' if mouse_grabbed else 'OFF (F1 toggle)'}",
            f"",
            f"HP:    {ps.get('health', '?')}",
            f"Pos:   {ps.get('x', 0):.1f}, {ps.get('y', 0):.1f}, {ps.get('z', 0):.1f}",
            f"Look:  yaw {ps.get('yaw', 0):.1f}  pitch {ps.get('pitch', 0):.1f}",
            f"Held:  {hi.get('name', 'air')} ({hi.get('category', '')})",
            f"",
            f"WASD=Move  Space=Jump  Shift=Sneak  Ctrl=Sprint",
            f"LClick=Attack  RClick=Use  1-9=Slot  Q=Drop",
            f"E=Inventory  F=Swap  V=Wheel  ESC=Quit",
        ]

        y = 10
        for i, line in enumerate(lines):
            color = (100, 200, 255) if i == 0 else (200, 200, 200)
            if not connected and i == 2:
                color = (255, 80, 80)
            surf = font.render(line, True, color)
            screen.blit(surf, (12, y))
            y += 20

        pygame.display.flip()
        clock.tick(FPS)

    # -- Cleanup --
    release_all()
    set_grab(False)
    pygame.quit()
    client.disconnect()
    print("Bye!")


if __name__ == "__main__":
    main()
