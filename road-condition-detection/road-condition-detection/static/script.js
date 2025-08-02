// Global variables
let isProcessing = false;
let stream = null;
let lastAlertTime = 0; // Track when the last alert was played
const ALERT_COOLDOWN = 5000; // 5 Seconds cooldown in milliseconds

// Handle file upload form submission
document.getElementById('uploadForm').onsubmit = async function(event) {
    event.preventDefault();

    const fileInput = document.getElementById('fileInput');
    const statusDiv = document.getElementById('status');
    const videoFeed = document.getElementById('videoFeed');
    const abortButton = document.getElementById('abortButton');

    if (fileInput.files.length === 0) {
        alert('Please select a file!');
        return;
    }

    // Stop the live camera feed if active
    stopCamera();

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    statusDiv.innerText = 'Uploading and starting live processing...';
    isProcessing = true;
    abortButton.style.display = 'block';

    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            throw new Error('Failed to process file.');
        }

        const result = await response.json();

        statusDiv.innerText = 'Live processing started!';
        videoFeed.src = result.video_feed;
        videoFeed.style.display = 'block';

        // Start listening for pothole detections
        startPotholeDetectionListener();

    } catch (error) {
        statusDiv.innerText = `Error: ${error.message}`;
        isProcessing = false;
        abortButton.style.display = 'none';
    }
};

// Handle abort processing button
document.getElementById('abortButton').onclick = async function() {
    if (isProcessing) {
        try {
            const response = await fetch('/abort', { method: 'POST' });

            if (response.ok) {
                isProcessing = false;
                document.getElementById('status').innerText = 'Processing aborted';
                document.getElementById('videoFeed').style.display = 'none';
                this.style.display = 'none';
            }
        } catch (error) {
            console.error('Failed to abort processing:', error);
        }
    }
};

// Start live camera feed processing
document.getElementById('startCamera').onclick = async function() {
    try {
        const videoFeed = document.getElementById('videoFeed');
        
        // Stop any ongoing file processing
        if (isProcessing) {
            await fetch('/abort', { method: 'POST' });
            isProcessing = false;
            document.getElementById('abortButton').style.display = 'none';
        }

        // Request backend to start camera
        const response = await fetch('/start_camera', { method: 'POST' });
        const data = await response.json();

        if (response.ok) {
            videoFeed.src = '/camera_feed';
            videoFeed.style.display = 'block';
            document.getElementById('status').innerText = 'Live camera processing started';
            document.getElementById('stopCamera').style.display = 'block';
            this.style.display = 'none';
            
            // Start listening for pothole detections
            startPotholeDetectionListener();
        } else {
            document.getElementById('status').innerText = `Error: ${data.error}`;
        }
    } catch (error) {
        document.getElementById('status').innerText = `Camera error: ${error.message}`;
    }
};

// Stop live camera feed
document.getElementById('stopCamera').onclick = function() {
    stopCamera();
};

// Function to stop the camera
function stopCamera() {
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
        stream = null;
    }
    
    fetch('/stop_camera', { method: 'POST' })
        .then(() => {
            document.getElementById('videoFeed').style.display = 'none';
            document.getElementById('status').innerText = 'Camera stopped';
            document.getElementById('stopCamera').style.display = 'none';
            document.getElementById('startCamera').style.display = 'block';
        })
        .catch(error => {
            console.error('Failed to stop camera:', error);
        });
}

// Display selected file name
document.getElementById('fileInput').addEventListener('change', function() {
    var fileName = this.files[0] ? this.files[0].name : 'No file chosen';
    document.getElementById('fileName').textContent = fileName;
});

// Function to play alert sound with cooldown
function playAlertSound() {
    const currentTime = Date.now();
    
    // Check if enough time has passed since the last alert
    if (currentTime - lastAlertTime > ALERT_COOLDOWN) {
        const alertSound = document.getElementById('alertSound');
        alertSound.play();
        lastAlertTime = currentTime;
        
        // Update status with alert info
        const statusDiv = document.getElementById('status');
        statusDiv.innerText = 'ALERT: Pothole detected!';
        statusDiv.style.backgroundColor = '#ffcccc';
        statusDiv.style.color = '#cc0000';
        
        // Reset status after 3 seconds
        setTimeout(() => {
            statusDiv.style.backgroundColor = '#e8f0fe';
            statusDiv.style.color = '#1a73e8';
            statusDiv.innerText = 'Processing active';
        }, 3000);
    }
}

// Function to start listening for pothole detections from the server
function startPotholeDetectionListener() {
    // Create an EventSource connection to the server for SSE (Server-Sent Events)
    const eventSource = new EventSource('/pothole_events');
    
    // Listen for pothole detection events
    eventSource.addEventListener('pothole_detected', function(event) {
        playAlertSound();
    });
    
    // Handle connection errors
    eventSource.onerror = function() {
        console.error('EventSource connection failed');
        eventSource.close();
    };
    
    // Stop the event source on page unload
    window.addEventListener('beforeunload', function() {
        eventSource.close();
    });
}
script.js