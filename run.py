from dotenv import load_dotenv

load_dotenv()

from app import create_app

app = create_app()

# if __name__ == '__main__':
#     app.run(debug=True)

if __name__ == '__main__':
    import os
    # debug=True exposes the Werkzeug debugger (remote code execution) to the whole LAN, so it is
    # opt-in: set FLASK_DEBUG=1 on your dev machine only, never on the phone.
    app.run(host='0.0.0.0', port=5000, debug=os.environ.get('FLASK_DEBUG', '0') == '1')