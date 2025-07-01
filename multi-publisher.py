import paho.mqtt.client as mqtt
import time
import random
import json
import string
from datetime import datetime
import threading
from decimal import Decimal
import argparse
import uuid

class MQTTPublisher:
    def __init__(self, broker="broker.hivemq.com", port=1883, publisher_id=None):
        self.broker = broker
        self.port = port
        self.publisher_id = publisher_id or f"publisher_{uuid.uuid4().hex[:8]}"
        self.data_topic = f"dicv/truck/sensor/data/{self.publisher_id}"
        self.config_topic = f"dicv/truck/control/config/{self.publisher_id}"
        self.status_topic = f"dicv/truck/status/{self.publisher_id}"
        
        # Default parameters with unique ranges per publisher
        self.default_params = {
            "speed": {"type": "number", "min": 0, "max": 120, "interval": random.uniform(2, 8)},
            "fuellevel": {"type": "number", "min": 10, "max": 100, "interval": random.uniform(3, 10)},
            "enginetemp": {"type": "number", "min": 60, "max": 110, "interval": random.uniform(4, 12)},
            "latitude": {"type": "number", "min": 12.8341, "max": 13.1414, "interval": random.uniform(8, 15)},
            "longitude": {"type": "number", "min": 77.4489, "max": 77.7845, "interval": random.uniform(8, 15)},
            "enginerpm": {"type": "number", "min": 800, "max": 3500, "interval": random.uniform(2, 6)},
            "batteryvoltage": {"type": "number", "min": 11.5, "max": 14.4, "interval": random.uniform(5, 15)},
            "odometer": {"type": "number", "min": 50000, "max": 500000, "interval": random.uniform(20, 60)},
            "enginestatus": {"type": "characters", "length": 8, "interval": random.uniform(10, 30)},
            "brakestatus": {"type": "characters", "length": 8, "interval": random.uniform(8, 25)},
            "doorstatus": {"type": "characters", "length": 8, "interval": random.uniform(15, 45)},
            "airpressure": {"type": "number", "min": 80, "max": 120, "interval": random.uniform(6, 18)}
        }
        
        self.param_config = self.default_params.copy()
        self.param_lock = threading.Lock()
        self.last_sent = {k: 0 for k in self.param_config}
        self.client = None
        self.connected = False
        self.running = False
        self.message_count = 0
        
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            print(f"✅ Publisher {self.publisher_id} connected to MQTT broker")
            client.subscribe(self.config_topic)
            
            # Publish initial status
            status_msg = {
                "publisher_id": self.publisher_id,
                "status": "online",
                "timestamp": datetime.now().isoformat(),
                "topics": {
                    "data": self.data_topic,
                    "config": self.config_topic,
                    "status": self.status_topic
                }
            }
            client.publish(self.status_topic, json.dumps(status_msg), retain=True)
            print(f"📡 Publisher {self.publisher_id} subscribed to: {self.config_topic}")
        else:
            print(f"❌ Publisher {self.publisher_id} failed to connect. RC: {rc}")

    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        print(f"📡 Publisher {self.publisher_id} disconnected")

    def on_message(self, client, userdata, msg):
        if msg.topic == self.config_topic:
            try:
                config = json.loads(msg.payload.decode())
                print(f"🔄 Publisher {self.publisher_id} received config: {config}")
                
                with self.param_lock:
                    self.param_config = config.copy()
                    self.last_sent = {k: 0 for k in config}
                
                print(f"🔄 Publisher {self.publisher_id} config updated")
            except Exception as e:
                print(f"❌ Publisher {self.publisher_id} config error: {e}")

    def generate_value(self, cfg, param_name):
        """Generate random value based on parameter configuration"""
        try:
            param_type = cfg.get("type", "number")
            
            if param_type == "number":
                min_val = float(cfg.get("min", 0))
                max_val = float(cfg.get("max", 100))
                
                if max_val > 1e15:
                    if min_val <= 0:
                        min_val = 1
                    
                    log_min = max(0, int(str(min_val).count('0') * 0.3))
                    log_max = min(30, int(str(int(max_val)).count('0') * 1.1))
                    
                    magnitude = random.randint(log_min, log_max)
                    mantissa = random.uniform(1, 9.99)
                    value = mantissa * (10 ** magnitude)
                    
                    value = max(min_val, min(value, max_val))
                    return int(value)
                else:
                    if max_val > min_val:
                        if max_val - min_val < 1:
                            return round(random.uniform(min_val, max_val), 2)
                        else:
                            return random.randint(int(min_val), int(max_val))
                    else:
                        return int(min_val)
                        
            elif param_type == "characters":
                length = max(1, min(int(cfg.get("length", 8)), 50))
                
                if "status" in param_name.lower():
                    statuses = ["ACTIVE", "IDLE", "WARNING", "ERROR", "OK", "FAILED", "READY", "BUSY", "NORMAL", "CRITICAL"]
                    selected_status = random.choice(statuses)
                    if len(selected_status) > length:
                        return selected_status[:length]
                    elif len(selected_status) < length:
                        return selected_status.ljust(length, 'X')
                    return selected_status
                else:
                    return ''.join(random.choices(string.ascii_uppercase, k=length))
            
            elif param_type == "alphanumeric":
                letters_length = max(1, min(int(cfg.get("lettersLength", 4)), 50))
                numbers_length = max(1, min(int(cfg.get("numbersLength", 4)), 50))
                letters_part = ''.join(random.choices(string.ascii_uppercase, k=letters_length))
                numbers_part = ''.join(random.choices(string.digits, k=numbers_length))
                return f"{letters_part} {numbers_part}"
            
            return 0
            
        except Exception as e:
            print(f"❌ Publisher {self.publisher_id} error generating value for {param_name}: {e}")
            return 0

    def start_publishing(self):
        """Start the publishing loop"""
        self.client = mqtt.Client(client_id=f"dicv_publisher_{self.publisher_id}")
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        
        try:
            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()
            time.sleep(2)
            
            self.running = True
            print(f"🚀 Publisher {self.publisher_id} started publishing to {self.data_topic}")
            
            while self.running:
                now = time.time()
                payload = {
                    "publisher_id": self.publisher_id,
                    "truckid": f"DICV_{self.publisher_id}_{random.randint(1000,9999)}",
                    "timestamp": datetime.now().isoformat(),
                    "data": {}
                }
                
                with self.param_lock:
                    for key, cfg in self.param_config.items():
                        interval = float(cfg.get("interval", 5))
                        if now - self.last_sent.get(key, 0) >= interval:
                            value = self.generate_value(cfg, key)
                            payload["data"][key] = value
                            self.last_sent[key] = now
                
                if payload["data"]:
                    try:
                        json_payload = json.dumps(payload, default=str)
                        self.client.publish(self.data_topic, json_payload, qos=1)
                        self.message_count += 1
                        
                        if self.message_count % 50 == 0:
                            print(f"📊 Publisher {self.publisher_id}: {self.message_count} messages sent")
                            
                    except Exception as e:
                        print(f"❌ Publisher {self.publisher_id} publish error: {e}")
                
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print(f"\n🛑 Stopping publisher {self.publisher_id}...")
        except Exception as e:
            print(f"❌ Publisher {self.publisher_id} error: {e}")
        finally:
            self.stop_publishing()

    def stop_publishing(self):
        """Stop the publishing loop"""
        self.running = False
        if self.client:
            # Send offline status
            status_msg = {
                "publisher_id": self.publisher_id,
                "status": "offline",
                "timestamp": datetime.now().isoformat(),
                "total_messages": self.message_count
            }
            self.client.publish(self.status_topic, json.dumps(status_msg), retain=True)
            self.client.loop_stop()
            self.client.disconnect()
        print(f"✅ Publisher {self.publisher_id} stopped after {self.message_count} messages")


def run_multiple_publishers(num_publishers=5, broker="broker.hivemq.com"):
    """Run multiple publishers concurrently"""
    publishers = []
    threads = []
    
    print(f"🚀 Starting {num_publishers} MQTT publishers...")
    print(f"🔗 Connecting to broker: {broker}")
    
    for i in range(num_publishers):
        publisher = MQTTPublisher(broker=broker, publisher_id=f"pub_{i+1:03d}")
        publishers.append(publisher)
        
        thread = threading.Thread(target=publisher.start_publishing, daemon=True)
        threads.append(thread)
        thread.start()
        
        time.sleep(0.5)  # Stagger connections
    
    try:
        print(f"✅ All {num_publishers} publishers started successfully")
        print("Press Ctrl+C to stop all publishers...")
        
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print(f"\n🛑 Stopping all {num_publishers} publishers...")
        for publisher in publishers:
            publisher.stop_publishing()
        
        for thread in threads:
            thread.join(timeout=2)
        
        print("✅ All publishers stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='DICV Multi-Publisher MQTT System')
    parser.add_argument('--publishers', '-p', type=int, default=5, help='Number of publishers to run')
    parser.add_argument('--broker', '-b', type=str, default='broker.hivemq.com', help='MQTT broker address')
    parser.add_argument('--port', type=int, default=1883, help='MQTT broker port')
    
    args = parser.parse_args()
    
    run_multiple_publishers(args.publishers, args.broker)
