const API_ENDPOINT = window.VAANI_API_ENDPOINT || '';

const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');
const recordButton = document.getElementById('recordButton');
const recordingStatus = document.getElementById('recordingStatus');
const loading = document.getElementById('loading');
const errorDiv = document.getElementById('error');

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

document.addEventListener('DOMContentLoaded', () => {
    if (!API_ENDPOINT) {
        showError('API endpoint is not configured. Set window.VAANI_API_ENDPOINT before loading this script.');
        sendButton.disabled = true;
        recordButton.disabled = true;
        return;
    }

    messageInput.focus();

    sendButton.addEventListener('click', sendTextMessage);
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendTextMessage();
    });

    recordButton.addEventListener('click', toggleRecording);
});

function escapeHtml(text) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

function addMessage(text, isUser, audioUrl) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message ' + (isUser ? 'user-message' : 'bot-message');

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    const senderStrong = document.createElement('strong');
    senderStrong.textContent = isUser ? 'You' : 'Vaani';
    contentDiv.appendChild(senderStrong);

    const textNode = document.createTextNode(' ' + text);
    contentDiv.appendChild(textNode);

    if (audioUrl && !isUser) {
        const audio = document.createElement('audio');
        audio.controls = true;
        audio.src = audioUrl;
        audio.autoplay = true;
        contentDiv.appendChild(audio);
    }

    messageDiv.appendChild(contentDiv);
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function setLoading(show) {
    loading.style.display = show ? 'block' : 'none';
    sendButton.disabled = show;
    messageInput.disabled = show;
}

function showError(message) {
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
    setTimeout(() => {
        errorDiv.style.display = 'none';
    }, 5000);
}

async function sendTextMessage() {
    const message = messageInput.value.trim();
    if (!message) return;

    addMessage(message, true, null);
    messageInput.value = '';

    setLoading(true);

    try {
        const response = await fetch(API_ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                type: 'text',
                text: message
            })
        });

        if (!response.ok) {
            throw new Error('HTTP ' + response.status + ': ' + response.statusText);
        }

        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || 'Unknown error');
        }

        let audioUrl = null;
        if (data.audio) {
            const audioBlob = base64ToBlob(data.audio, 'audio/mpeg');
            audioUrl = URL.createObjectURL(audioBlob);
        }

        addMessage(data.text, false, audioUrl);

    } catch (error) {
        showError('Request failed. Please try again.');
        addMessage('Sorry, something went wrong. Please try again.', false, null);
    } finally {
        setLoading(false);
    }
}

async function toggleRecording() {
    if (!isRecording) {
        await startRecording();
    } else {
        stopRecording();
    }
}

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = (event) => {
            audioChunks.push(event.data);
        };

        mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            await sendVoiceMessage(audioBlob);
            stream.getTracks().forEach(track => track.stop());
        };

        mediaRecorder.start();
        isRecording = true;
        recordButton.textContent = 'Stop';
        recordButton.style.background = '#dc3545';
        recordingStatus.style.display = 'block';

    } catch (error) {
        showError('Microphone access denied. Please allow microphone access and try again.');
    }
}

function stopRecording() {
    if (mediaRecorder && isRecording) {
        mediaRecorder.stop();
        isRecording = false;
        recordButton.textContent = 'Mic';
        recordButton.style.background = '';
        recordingStatus.style.display = 'none';
    }
}

async function sendVoiceMessage(audioBlob) {
    addMessage('Processing voice input...', true, null);

    setLoading(true);

    try {
        const base64Audio = await blobToBase64(audioBlob);

        const response = await fetch(API_ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                type: 'voice',
                audio: base64Audio
            })
        });

        if (!response.ok) {
            throw new Error('HTTP ' + response.status + ': ' + response.statusText);
        }

        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || 'Unknown error');
        }

        if (data.transcription) {
            addMessage('You said: ' + data.transcription, true, null);
        }

        let audioUrl = null;
        if (data.audio) {
            const audioResponseBlob = base64ToBlob(data.audio, 'audio/mpeg');
            audioUrl = URL.createObjectURL(audioResponseBlob);
        }

        addMessage(data.text, false, audioUrl);

    } catch (error) {
        showError('Could not process voice input. Please try again.');
        addMessage('Sorry, could not process voice input. Please try again.', false, null);
    } finally {
        setLoading(false);
    }
}

function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const base64 = reader.result.split(',')[1];
            resolve(base64);
        };
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });
}

function base64ToBlob(base64, mimeType) {
    const byteCharacters = atob(base64);
    const byteNumbers = new Array(byteCharacters.length);
    for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
    }
    const byteArray = new Uint8Array(byteNumbers);
    return new Blob([byteArray], { type: mimeType });
}
