from flask import Flask, send_from_directory, request, jsonify, render_template
from mcstatus import JavaServer
import logging
import re
import json
import os
import time
from threading import Thread

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# File to store servers
SERVERS_FILE = 'servers.json'

# Load servers from file
def load_servers():
    if os.path.exists(SERVERS_FILE):
        with open(SERVERS_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

# Save servers to file
def save_servers(servers):
    with open(SERVERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(servers, f, ensure_ascii=False, indent=2)

# Ping a server and return status
def ping_server(address):
    try:
        if ':' not in address:
            address += ':25565'
            
        host, port = address.split(':', 1)
        port = int(port)
        
        server = JavaServer(host, port)
        status = server.status()
        
        return {
            'status': 'online',
            'version': status.version.name,
            'players_online': status.players.online,
            'players_max': status.players.max,
            'description': str(status.description),
            'latency': status.latency,
            'last_checked': time.time(),
            'address': address
        }
    except Exception as e:
        return {
            'status': 'offline',
            'error': str(e),
            'address': address,
            'last_checked': time.time()
        }

# Background thread to check servers
def server_checker():
    while True:
        try:
            servers = load_servers()
            updated_servers = []
            
            for server in servers:
                # Only check servers that were added more than 5 minutes ago
                if time.time() - server.get('added_time', 0) > 300:
                    status = ping_server(server['address'])
                    # Keep online servers
                    if status['status'] == 'online':
                        # Update server info
                        server.update(status)
                        updated_servers.append(server)
                else:
                    # Keep new servers without rechecking
                    updated_servers.append(server)
            
            save_servers(updated_servers)
            app.logger.info(f"Server check completed. Online: {len(updated_servers)}")
        except Exception as e:
            app.logger.error(f"Server checker error: {str(e)}")
        
        # Wait 5 minutes before next check
        time.sleep(300)

# Start background checker
if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    checker_thread = Thread(target=server_checker)
    checker_thread.daemon = True
    checker_thread.start()

# Serve static files from root
@app.route('/<path:filename>')
def static_files(filename):
    # Prevent serving media files through this route
    if filename.startswith('media/'):
        return "Not Found", 404
    return send_from_directory('.', filename)

# Serve media files specifically
@app.route('/media/<path:filename>')
def media_files(filename):
    return send_from_directory('media', filename)

# Main page
@app.route('/')
def serve_index():
    servers = load_servers()
    
    # Format added time as "X minutes ago"
    for server in servers:
        added_time = server.get('added_time', time.time())
        minutes_ago = int((time.time() - added_time) / 60)
        server['added_str'] = f"{minutes_ago} минут назад" if minutes_ago > 0 else "только что"
    
    return render_template('index.html', servers=servers)

# Add server page
@app.route('/add-server')
def serve_add_server():
    return send_from_directory('.', 'index2.html')

# Handle server ping request
@app.route('/add-server', methods=['POST'])
def add_server():
    address = request.form.get('address', '').strip()
    if not address:
        return jsonify({'error': 'Не введено название сервера'}), 400
    
    # Validate address format
    if not re.match(r'^[\w\.\-]+(:\d+)?$', address):
        return jsonify({'error': 'Неверный формат адреса'}), 400
    
    # Ping server
    server_info = ping_server(address)
    
    if server_info['status'] == 'online':
        # Add to servers list
        servers = load_servers()
        
        # Check if server already exists
        if not any(s['address'] == server_info['address'] for s in servers):
            server_info['added_time'] = time.time()
            servers.append(server_info)
            save_servers(servers)
        
        # Prepare HTML response
        html_response = f"""
        <div class="server-stats" style="margin-top: 20px; padding: 15px; background: #f8f8f8; border-radius: 5px;">
            <h3>Статус сервера</h3>
            <p><strong>Адрес:</strong> {address}</p>
            <p><strong>Статус:</strong> <span style="color: green; font-weight: bold;">Онлайн ✓</span></p>
            <p><strong>Версия:</strong> {server_info['version']}</p>
            <p><strong>Игроки:</strong> {server_info['players_online']}/{server_info['players_max']}</p>
            <p><strong>Задержка:</strong> {server_info['latency']:.2f} ms</p>
            <p><strong>Описание:</strong> {server_info['description']}</p>
            <p style="color: green; font-weight: bold;">Сервер добавлен в мониторинг!</p>
        </div>
        """
        
        return jsonify({'html': html_response})
    
    else:
        return jsonify({
            'error': f'<div class="error" style="color:red; margin-top:20px;">Сервер не отвечает: {server_info.get("error", "Unknown error")}</div>'
        })

if __name__ == '__main__':
    app.run(debug=True, port=5000, use_reloader=False)