import threading

# We use a try-except block so the app NEVER crashes if the notification library fails
try:
    from win10toast_persist import ToastNotifier
    HAS_TOAST = True
except ImportError:
    HAS_TOAST = False
    print("⚠️ Warning: Notification libraries missing. Desktop alerts will print to console instead.")

def send_alert(title, message, duration=10):
    """Sends a Windows Desktop notification, or prints to console if unavailable."""
    if not HAS_TOAST:
        # Fallback: Print to the black terminal window
        print(f"\n🔔 [SYSTEM ALERT] {title}: {message}\n")
        return

    def show():
        try:
            toaster = ToastNotifier()
            toaster.show_toast(title, message, duration=duration, threaded=False)
        except Exception as e:
            print(f"Notification Error: {e}")
            
    # Run in a background thread
    threading.Thread(target=show, daemon=True).start()