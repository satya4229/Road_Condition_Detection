from flask import Flask, render_template, Response, request, jsonify, url_for, stream_with_context
import cv2
import os
import threading
import time
from werkzeug.utils import secure_filename
from ultralytics import YOLO
import numpy as np
import queue

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')

# Folders for uploads and processed files
UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'

# Ensure folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

# Load YOLO model
# MODEL_PATH = os.path.join(os.getcwd(), 'best.pt')
# model = YOLO(MODEL_PATH)
 

# Get the current script's directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Define the correct path to best.pt
MODEL_PATH = os.path.join(BASE_DIR, "best.pt")

# Debugging: Print the model path to verify
print(f"Checking model path: {MODEL_PATH}")

# Ensure the file exists
if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"Model file not found at {MODEL_PATH}")
model = YOLO(MODEL_PATH)


# Global variables
video_path = None
camera = None
processing_active = False
camera_active = False

# Queue for pothole detection events
pothole_events = queue.Queue()

def process_frame(frame):
    """Process a single frame with YOLO model and detect potholes"""
    try:
        # Ensure frame is in BGR format
        if len(frame.shape) == 2:  # If grayscale
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        
        # Ensure proper frame dimensions
        if frame.shape[0] == 0 or frame.shape[1] == 0:
            raise ValueError("Invalid frame dimensions")

        # Run YOLO detection
        results = model(frame)
        
        pothole_detected = False
        
        # Draw detections
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                cls = int(box.cls[0])
                
                # Draw bounding box and label
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"{model.names[cls]} {conf:.2f}"
                # Add background to text for better visibility
                (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                cv2.rectangle(frame, (x1, y1 - 20), (x1 + w, y1), (0, 255, 0), -1)
                cv2.putText(frame, label, (x1, y1 - 5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
                
                # Check if object is a pothole (assuming class name or index)
                if model.names[cls].lower() == 'pothole' and conf > 0.5:
                    pothole_detected = True
        
        # If pothole detected, add event to queue
        if pothole_detected:
            pothole_events.put({"timestamp": time.time()})
        
        return frame
    except Exception as e:
        print(f"Error processing frame: {e}")
        return frame

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    global video_path, processing_active, camera_active
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    # Stop camera if it's running
    if camera_active:
        stop_camera()
    
    filename = secure_filename(file.filename)
    video_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(video_path)
    
    processing_active = True
    return jsonify({'message': 'File uploaded successfully', 
                   'video_feed': '/video_feed'})

@app.route('/start_camera', methods=['POST'])
def start_camera():
    global camera, camera_active, processing_active, video_path
    
    # Stop any ongoing video processing
    processing_active = False
    video_path = None
    
    try:
        if camera is not None:
            camera.release()
        
        # Try different camera backends
        camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # Try DirectShow first
        if not camera.isOpened():
            camera = cv2.VideoCapture(0)  # Fallback to default
        
        if not camera.isOpened():
            return jsonify({'error': 'Failed to open camera'}), 500
        
        # Set camera properties
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        camera.set(cv2.CAP_PROP_FPS, 30)
        camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        
        # Read test frame
        ret, frame = camera.read()
        if not ret or frame is None:
            raise Exception("Failed to read test frame from camera")
        
        camera_active = True
        return jsonify({'message': 'Camera started'})
    
    except Exception as e:
        if camera is not None:
            camera.release()
            camera = None
        return jsonify({'error': f'Camera error: {str(e)}'}), 500

# @app.route('/stop_camera', methods=['POST'])
# def stop_camera():
#     global camera, camera_active
    
#     camera_active = False
#     if camera is not None:
#         camera.release()
#         camera = None
    
#     return jsonify({'message': 'Camera stopped'})
@app.route('/stop_camera', methods=['POST'])
def stop_camera():
    global camera, camera_active
    
    if camera is not None:
        camera.release()
        camera = None
    
    camera_active = False
    return jsonify({'message': 'Camera stopped successfully'})


def generate_frames():
    global video_path, processing_active
    
    if not video_path or not os.path.exists(video_path):
        return
    
    cap = cv2.VideoCapture(video_path)
    
    while cap.isOpened() and processing_active:
        success, frame = cap.read()
        if not success:
            break
        
        processed_frame = process_frame(frame)
        _, buffer = cv2.imencode('.jpg', processed_frame)
        frame_bytes = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    
    cap.release()

def generate_camera_frames():
    global camera, camera_active

    while camera_active and camera is not None:
        try:
            success, frame = camera.read()
            if not success or frame is None:
                print("Failed to read camera frame")
                break
            
            # Ensure frame has valid dimensions
            if frame.shape[0] == 0 or frame.shape[1] == 0:
                continue
                
            processed_frame = process_frame(frame)
            _, buffer = cv2.imencode('.jpg', processed_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            frame_bytes = buffer.tobytes()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

        except Exception as e:
            print(f"Error in generate_camera_frames: {e}")
            break
    
    if camera is not None:
        camera.release()
        camera = None

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/camera_feed')
def camera_feed():
    return Response(generate_camera_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/abort', methods=['POST'])
def abort_processing():
    global processing_active, camera_active
    processing_active = False
    camera_active = False
    return jsonify({'message': 'Processing aborted'})

@app.route('/pothole_events')
def pothole_event_stream():
    """Server-sent events stream for pothole detections"""
    def event_generator():
        while processing_active or camera_active:
            try:
                # Non-blocking check for pothole events
                try:
                    event = pothole_events.get(block=False)
                    # Format as SSE message
                    yield f"event: pothole_detected\ndata: {{'timestamp': {event['timestamp']}}}\n\n"
                except queue.Empty:
                    pass
                
                # Sleep briefly to avoid CPU spinning
                time.sleep(0.1)
            except Exception as e:
                print(f"Error in event stream: {e}")
                break
        
        # Final message to close connection
        yield "event: close\ndata: Connection closed\n\n"
    
    return Response(stream_with_context(event_generator()),
                   mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True, threaded=True)
