import paho.mqtt.client as mqtt
import json
from datetime import datetime
import threading
import time
import queue
import argparse
import uuid
from collections import defaultdict

class MQTTSubscriber:
    def __init__(self, broker="broker.hivemq.com", port=1883, subscriber_id=None, filter_config=None):
        self.broker = broker
        self.port = port
        self.subscriber_id = subscriber_id or f"subscriber_{uuid.uuid4().hex[:8]}"
        self.filter_config = filter_config or {}
        
        # Topic patterns for subscription
        self.data_topic_pattern = "dicv/truck/sensor/data/+"
        self.status_topic_pattern = "dicv/truck/status/+"
        self.control_topic = f"dicv/subscriber/control/{self.subscriber_id}"
        
        self.client = None
        self.connected = False
        self.running = False
        self.message_queue = queue.Queue()
        self.message_count = 0
        self.publisher_stats = defaultdict(int)
        self.filtered_messages = 0
        
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            print(f"✅ Subscriber {self.subscriber_id} connected to MQTT broker")
            
            # Subscribe to data and status topics
            client.subscribe(self.data_topic_pattern, qos=1)
            client.subscribe(self.status_topic_pattern, qos=1)
            client.subscribe(self.control_topic, qos=1)
            
            print(f"📡 Subscriber {self.subscriber_id} subscribed to:")
            print(f"   - Data: {self.data_topic_pattern}")
            print(f"   - Status: {self.status_topic_pattern}")
            print(f"   - Control: {self.control_topic}")
        else:
            print(f"❌ Subscriber {self.subscriber_id} failed to connect. RC: {rc}")

    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        print(f"📡 Subscriber {self.subscriber_id} disconnected")

    def on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
            
            if "sensor/data" in msg.topic:
                # Handle sensor data messages
                if self.should_process_message(data):
                    self.message_queue.put(("data", msg.topic, data, datetime.now()))
                    self.message_count += 1
                    
                    publisher_id = data.get("publisher_id", "unknown")
                    self.publisher_stats[publisher_id] += 1
                else:
                    self.filtered_messages += 1
                    
            elif "status" in msg.topic:
                # Handle status messages
                self.message_queue.put(("status", msg.topic, data, datetime.now()))
                
            elif msg.topic == self.control_topic:
                # Handle control messages
                self.handle_control_message(data)
                
        except json.JSONDecodeError:
            print(f"❌ Subscriber {self.subscriber_id}: Invalid JSON from {msg.topic}")
        except Exception as e:
            print(f"❌ Subscriber {self.subscriber_id}: Error processing message: {e}")

    def should_process_message(self, data):
        """Apply filtering based on subscriber configuration"""
        if not self.filter_config:
            return True
            
        # Filter by publisher ID
        if "publisher_ids" in self.filter_config:
            publisher_id = data.get("publisher_id", "")
            if publisher_id not in self.filter_config["publisher_ids"]:
                return False
        
        # Filter by parameter ranges
        if "parameter_filters" in self.filter_config:
            sensor_data = data.get("data", {})
            for param, filter_rule in self.filter_config["parameter_filters"].items():
                if param in sensor_data:
                    value = sensor_data[param]
                    if isinstance(value, (int, float)):
                        min_val = filter_rule.get("min")
                        max_val = filter_rule.get("max")
                        if min_val is not None and value < min_val:
                            return False
                        if max_val is not None and value > max_val:
                            return False
        
        # Filter by truck ID pattern
        if "truck_id_pattern" in self.filter_config:
            truck_id = data.get("truckid", "")
            pattern = self.filter_config["truck_id_pattern"]
            if pattern not in truck_id:
                return False
        
        return True

    def handle_control_message(self, data):
        """Handle control messages to update subscriber configuration"""
        try:
            if data.get("action") == "update_filter":
                self.filter_config = data.get("filter_config", {})
                print(f"🔄 Subscriber {self.subscriber_id}: Filter config updated")
                
            elif data.get("action") == "get_stats":
                stats = {
                    "subscriber_id": self.subscriber_id,
                    "total_messages": self.message_count,
                    "filtered_messages": self.filtered_messages,
                    "publisher_stats": dict(self.publisher_stats),
                    "timestamp": datetime.now().isoformat()
                }
                print(f"📊 Subscriber {self.subscriber_id} stats: {stats}")
                
        except Exception as e:
            print(f"❌ Subscriber {self.subscriber_id}: Control message error: {e}")

    def process_messages(self):
        """Process messages from the queue"""
        while self.running:
            try:
                if not self.message_queue.empty():
                    msg_type, topic, data, timestamp = self.message_queue.get(timeout=1)
                    self.display_message(msg_type, topic, data, timestamp)
                else:
                    time.sleep(0.1)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ Subscriber {self.subscriber_id}: Message processing error: {e}")

    def display_message(self, msg_type, topic, data, timestamp):
        """Display received message"""
        if msg_type == "data":
            if self.message_count % 100 == 0:  # Display every 100th message to avoid spam
                print(f"\n📨 Subscriber {self.subscriber_id} - Message #{self.message_count}")
                print(f"🕒 {timestamp.strftime('%H:%M:%S')}")
                print(f"📍 Topic: {topic}")
                print(f"🚛 Truck: {data.get('truckid', 'Unknown')}")
                print(f"🏭 Publisher: {data.get('publisher_id', 'Unknown')}")
                
                # Show sample of sensor data
                sensor_data = data.get('data', {})
                sample_data = list(sensor_data.items())[:3]
                if sample_data:
                    sample_str = ", ".join([f"{k}: {v}" for k, v in sample_data])
                    print(f"📊 Sample Data: {sample_str}")
                print("-" * 60)
                
        elif msg_type == "status":
            publisher_id = data.get("publisher_id", "Unknown")
            status = data.get("status", "Unknown")
            print(f"📡 Publisher {publisher_id} status: {status}")

    def start_subscribing(self):
        """Start the subscribing loop"""
        self.client = mqtt.Client(client_id=f"dicv_subscriber_{self.subscriber_id}")
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        
        try:
            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()
            
            self.running = True
            
            # Start message processing thread
            processing_thread = threading.Thread(target=self.process_messages, daemon=True)
            processing_thread.start()
            
            print(f"🚀 Subscriber {self.subscriber_id} started")
            
            # Stats reporting loop
            last_stats_time = time.time()
            while self.running:
                time.sleep(1)
                
                # Report stats every 30 seconds
                if time.time() - last_stats_time > 30:
                    print(f"📊 Subscriber {self.subscriber_id}: {self.message_count} messages received, {self.filtered_messages} filtered")
                    last_stats_time = time.time()
                    
        except KeyboardInterrupt:
            print(f"\n🛑 Stopping subscriber {self.subscriber_id}...")
        except Exception as e:
            print(f"❌ Subscriber {self.subscriber_id} error: {e}")
        finally:
            self.stop_subscribing()

    def stop_subscribing(self):
        """Stop the subscribing loop"""
        self.running = False
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
        print(f"✅ Subscriber {self.subscriber_id} stopped after {self.message_count} messages")


def create_subscriber_configs(num_subscribers):
    """Create different filter configurations for subscribers"""
    configs = []
    
    for i in range(num_subscribers):
        if i == 0:
            # General subscriber - no filters
            config = {}
        elif i == 1:
            # Speed monitoring subscriber
            config = {
                "parameter_filters": {
                    "speed": {"min": 50, "max": 120},
                    "enginerpm": {"min": 2000}
                }
            }
        elif i == 2:
            # Engine health subscriber
            config = {
                "parameter_filters": {
                    "enginetemp": {"min": 80},
                    "batteryvoltage": {"max": 12.5}
                }
            }
        elif i == 3:
            # Location tracking subscriber
            config = {
                "parameter_filters": {
                    "latitude": {"min": 12.9, "max": 13.1},
                    "longitude": {"min": 77.5, "max": 77.7}
                }
            }
        else:
            # Publisher-specific subscribers
            publisher_num = ((i - 4) % 5) + 1
            config = {
                "publisher_ids": [f"pub_{publisher_num:03d}"]
            }
        
        configs.append(config)
    
    return configs


def run_multiple_subscribers(num_subscribers=5, broker="broker.hivemq.com"):
    """Run multiple subscribers concurrently"""
    subscribers = []
    threads = []
    
    print(f"🚀 Starting {num_subscribers} MQTT subscribers...")
    print(f"🔗 Connecting to broker: {broker}")
    
    # Create different configurations for subscribers
    configs = create_subscriber_configs(num_subscribers)
    
    for i in range(num_subscribers):
        subscriber = MQTTSubscriber(
            broker=broker, 
            subscriber_id=f"sub_{i+1:03d}",
            filter_config=configs[i]
        )
        subscribers.append(subscriber)
        
        thread = threading.Thread(target=subscriber.start_subscribing, daemon=True)
        threads.append(thread)
        thread.start()
        
        time.sleep(0.3)  # Stagger connections
    
    try:
        print(f"✅ All {num_subscribers} subscribers started successfully")
        print("📊 Subscriber configurations:")
        for i, config in enumerate(configs):
            config_desc = "General (no filters)" if not config else str(config)
            print(f"   - Subscriber {i+1}: {config_desc}")
        
        print("\nPress Ctrl+C to stop all subscribers...")
        
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print(f"\n🛑 Stopping all {num_subscribers} subscribers...")
        for subscriber in subscribers:
            subscriber.stop_subscribing()
        
        for thread in threads:
            thread.join(timeout=2)
        
        print("✅ All subscribers stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='DICV Multi-Subscriber MQTT System')
    parser.add_argument('--subscribers', '-s', type=int, default=5, help='Number of subscribers to run')
    parser.add_argument('--broker', '-b', type=str, default='broker.hivemq.com', help='MQTT broker address')
    parser.add_argument('--port', type=int, default=1883, help='MQTT broker port')
    
    args = parser.parse_args()
    
    run_multiple_subscribers(args.subscribers, args.broker)
