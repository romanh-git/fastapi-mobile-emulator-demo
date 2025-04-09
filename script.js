const API_BASE_URL = 'http://localhost:8000'; // Your FastAPI backend URL
const WS_URL = 'ws://localhost:8000/ws/logs'; // Your WebSocket endpoint

// --- State ---
let currentUsername = null; // Keep track of logged-in user
let ws = null; // WebSocket connection object

// --- DOM Elements ---
const usernameInput = document.getElementById('username');
const passwordInput = document.getElementById('password');
const llmPromptInput = document.getElementById('llm-prompt');
const userResponseArea = document.getElementById('user-response');
const logDisplayArea = document.getElementById('logDisplay');

// --- Helper Functions ---
function displayUserResponse(message, isError = false) {
    userResponseArea.innerHTML = `<p class="${isError ? 'error' : 'success'}">${escapeHtml(message)}</p>`;
}

function appendLog(logData) {
    if (!logDisplayArea) return;
    try {
        let formattedLog;
        if (typeof logData === 'string') {
             // Might be a raw message from WebSocket setup/error
             formattedLog = escapeHtml(logData);
        } else if (logData.system) {
             // System messages from the script itself
             formattedLog = `[SYSTEM] ${escapeHtml(logData.system)} ${logData.error ? `Error: ${escapeHtml(logData.error)}` : ''}`;
        }
        else {
            // Format log data from backend for better readability
            const time = new Date(logData.timestamp).toLocaleTimeString();
            const source = logData.source?.toUpperCase() || 'UNKNOWN';
            const method = logData.method || '';
            const url = logData.url || '';
            const status = logData.status || '';
            const reqPayload = logData.request_payload ? `\n  Request: ${JSON.stringify(logData.request_payload)}` : '';
            const resPayload = logData.response_payload ? `\n  Response: ${JSON.stringify(logData.response_payload)}` : '';
            const detail = logData.detail ? `\n  Detail: ${logData.detail}` : '';

            formattedLog = `[${time}] ${source} ${method} ${url} ${status}${reqPayload}${resPayload}${detail}`;
        }

        const logEntry = document.createElement('div');
        logEntry.textContent = formattedLog;
        logDisplayArea.appendChild(logEntry);

        // Auto-scroll to bottom
        logDisplayArea.scrollTop = logDisplayArea.scrollHeight;

    } catch (error) {
        console.error("Error appending log:", error);
        const errorEntry = document.createElement('div');
        errorEntry.textContent = `[SYSTEM] Error displaying log: ${error}`;
        errorEntry.style.color = 'red';
        logDisplayArea.appendChild(errorEntry);
        logDisplayArea.scrollTop = logDisplayArea.scrollHeight;
    }
}

// Basic HTML escaping
function escapeHtml(unsafe) {
    if (unsafe === null || unsafe === undefined) return '';
    return unsafe
         .toString()
         .replace(/&/g, "&")
         .replace(/</g, "<")
         .replace(/>/g, ">")
         .replace(/"/g, "&quot;")
         .replace(/'/g, "'");
}


// --- API Call Functions ---

async function makeApiRequest(endpoint, method = 'GET', body = null) {
    const url = `${API_BASE_URL}${endpoint}`;
    const options = {
        method: method,
        headers: {
            'Content-Type': 'application/json',
            // Add Authorization header here if using JWT/Tokens in a real app
        },
    };
    if (body) {
        options.body = JSON.stringify(body);
    }

    try {
        const response = await fetch(url, options);
        const data = await response.json(); // Attempt to parse JSON regardless of status

        if (!response.ok) {
            // Use detail from JSON response if available, otherwise use status text
            const errorMessage = data.detail || response.statusText || `HTTP error ${response.status}`;
            throw new Error(errorMessage);
        }
        return data; // Return parsed JSON data on success
    } catch (error) {
        console.error(`API Error (${method} ${endpoint}):`, error);
        // Re-throw the error with a clearer message if possible
        throw new Error(`Failed to ${method} ${endpoint}: ${error.message}`);
    }
}

async function registerUser() {
    const username = usernameInput.value.trim();
    const password = passwordInput.value.trim();
    if (!username || !password) {
        displayUserResponse("Username and password are required.", true);
        return;
    }
    try {
        const data = await makeApiRequest('/register/', 'POST', { username, password });
        displayUserResponse(data.message || "Registration successful!");
    } catch (error) {
        displayUserResponse(error.message, true);
    }
}

async function loginUser() {
    const username = usernameInput.value.trim();
    const password = passwordInput.value.trim();
    if (!username || !password) {
        displayUserResponse("Username and password are required.", true);
        return;
    }
    try {
        const data = await makeApiRequest('/login/', 'POST', { username, password });
        currentUsername = username; // Store username on successful login
        displayUserResponse(data.message || `Login successful! Welcome ${username}.`);
        // Maybe update UI to show logged-in state
    } catch (error) {
        currentUsername = null; // Clear username on failed login
        displayUserResponse(error.message, true);
    }
}

async function getUserInfo() {
    const username = usernameInput.value.trim(); // Use username from input field
    if (!username) {
         displayUserResponse("Enter a username to get info for.", true);
         return;
    }
    // You could also use `currentUsername` if you only want info for the logged-in user
    // if (!currentUsername) {
    //     displayUserResponse("Please log in first.", true);
    //     return;
    // }
    try {
        const data = await makeApiRequest(`/user/${encodeURIComponent(username)}/`, 'GET');
        displayUserResponse(`User Info: Username: ${data.username}`);
    } catch (error) {
        displayUserResponse(error.message, true);
    }
}

async function updateUser() {
    const username = usernameInput.value.trim(); // Use username from input field
    const password = passwordInput.value.trim(); // Use password field for the *new* password
     if (!username || !password) {
        displayUserResponse("Username and new password are required.", true);
        return;
    }
    // Add check: In a real app, you'd likely need the *old* password too,
    // and ensure the user updating is the logged-in user (`currentUsername`).
    // if (username !== currentUsername) {
    //    displayUserResponse("Cannot update password for another user.", true);
    //    return;
    // }

    try {
        const data = await makeApiRequest(`/user/${encodeURIComponent(username)}/`, 'PUT', { password });
        displayUserResponse(data.message || "Password updated successfully!");
        passwordInput.value = ''; // Clear password field after update
    } catch (error) {
        displayUserResponse(error.message, true);
    }
}

async function sendLLMPrompt() {
    const prompt = llmPromptInput.value.trim();
    if (!prompt) {
        displayUserResponse("Please enter a prompt for the LLM.", true);
        return;
    }
    if (!currentUsername) {
        displayUserResponse("Please log in before using the LLM.", true);
        return;
    }

    displayUserResponse("Sending prompt to LLM..."); // Indicate loading

    try {
        const data = await makeApiRequest('/llm/generate', 'POST', { username: currentUsername, prompt });
        // Display LLM response clearly
        userResponseArea.innerHTML = `<p><strong>LLM Response:</strong></p><p>${escapeHtml(data.text)}</p>`;
        // llmPromptInput.value = ''; // Optional: Clear prompt after sending
    } catch (error) {
        displayUserResponse(`LLM Error: ${error.message}`, true);
    }
}


// --- WebSocket Setup ---
function setupWebSocket() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        console.log("WebSocket already open or connecting.");
        return;
    }

    ws = new WebSocket(WS_URL);
    appendLog({ system: 'Attempting WebSocket connection...' }); // Use object format

    ws.onopen = () => {
        console.log('WebSocket connection established');
        appendLog({ system: 'WebSocket connection established.' });
    };

    ws.onmessage = (event) => {
        try {
            const logData = JSON.parse(event.data);
            appendLog(logData);
        } catch (error) {
            console.error('Failed to parse WebSocket message:', event.data, error);
            appendLog({ system: 'Received non-JSON WebSocket message', data: event.data });
        }
    };

    ws.onerror = (error) => {
        console.error('WebSocket Error:', error);
        // The 'error' event itself doesn't contain much detail usually.
        // The 'close' event often follows with more specific info.
        appendLog({ system: 'WebSocket error occurred.' });
    };

    ws.onclose = (event) => {
        console.log(`WebSocket connection closed: Code=${event.code}, Reason='${event.reason}', Clean=${event.wasClean}`);
        appendLog({ system: `WebSocket connection closed (Code: ${event.code}). Reconnecting in 5s...` });
        ws = null; // Clear the ws variable
        // Simple exponential backoff could be added here, but basic retry for demo:
        setTimeout(setupWebSocket, 5000); // Attempt to reconnect after 5 seconds
    };
}


// --- Initialisation ---
document.addEventListener('DOMContentLoaded', () => {
    // Clear log display on load
    if (logDisplayArea) {
        logDisplayArea.innerHTML = '';
    }
    setupWebSocket(); // Start WebSocket connection when the page loads
});