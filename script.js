const messagesContainer = document.getElementById("messages");
const input = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const chatForm = document.getElementById("chatForm");
const welcome = document.getElementById("welcome");
const chatList = document.getElementById("chatList");
const modelSelect = document.getElementById("modelSelect");
const toast = document.getElementById("toast");

let chats = [];
let activeChatId = null;
let isWaiting = false;

// function createChat() {
//     const chat = {
//         id: crypto.randomUUID(),
//         title: "New chat",
//         messages: []
//     };

//     chats.unshift(chat);
//     activeChatId = chat.id;

//     renderChatList();
//     renderMessages();

//     input.focus();
// }
async function createChat() {
    if (isWaiting) return;

    const response = await fetch("/api/conversations", {
        method: "POST"
    });

    if (response.status === 401) {
        window.location.href = "/login.html";
        return;
    }

    if (!response.ok) {
        showToast("Couldn't create conversation.");
        return;
    }

    const chat = await response.json();
    chat.messages = [];

    chats.unshift(chat);
    activeChatId = chat.id;

    renderChatList();
    renderMessages();
    input.focus();
}
function getActiveChat() {
    return chats.find(chat => chat.id === activeChatId);
}

// function renderChatList() {
//     chatList.replaceChildren();

//     chats.forEach(chat => {
//         const button = document.createElement("button");
//         button.className = "chat-item";
//         button.textContent = chat.title;
//         button.title = chat.title;

//         if (chat.id === activeChatId) {
//             button.classList.add("active");
//         }

//         button.addEventListener("click", () => {
//             if (isWaiting) return;

//             activeChatId = chat.id;
//             renderChatList();
//             renderMessages();
//         });

//         chatList.appendChild(button);
//     });
// }
function renderChatList() {
    chatList.replaceChildren();

    chats
        .filter(chat => chat.messages && chat.messages.length > 0)
        .forEach(chat => {
            const button = document.createElement("button");
            button.className = "chat-item";
            button.textContent = chat.title;
            button.title = chat.title;

            if (chat.id === activeChatId) {
                button.classList.add("active");
            }

            button.addEventListener("click", async () => {
                if (isWaiting) return;

                activeChatId = chat.id;

                const response = await fetch(
                    `/api/conversations/${chat.id}/messages`
                );

                if (!response.ok) {
                    showToast("Couldn't load conversation.");
                    return;
                }

                chat.messages = await response.json();

                renderChatList();
                renderMessages();
            });

            chatList.appendChild(button);
        });
}
function renderMessages() {
    const chat = getActiveChat();

    messagesContainer.replaceChildren();
    welcome.hidden = Boolean(chat && chat.messages.length);

    if (!chat) return;

    chat.messages.forEach(message => {
        const element = document.createElement("div");
        element.className = `message ${message.role}`;
        element.textContent = message.content;
        messagesContainer.appendChild(element);
    });

    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// async function getGeminiReply(messages) {
//     const response = await fetch("/api/chat", {
//         method: "POST",
//         headers: {
//             "Content-Type": "application/json"
//         },
//         body: JSON.stringify({ messages })
//     });

//     const data = await response.json();

//     if (!response.ok) {
//         throw new Error(data.detail || "Gemini request failed");
//     }

//     return data.reply;
// }
async function getGeminiReply(chat) {
    const response = await fetch("/api/chat", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            conversation_id: chat.id,
            messages: chat.messages
        })
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.detail || "Chat request failed");
    }

    return data.reply;
}
async function loadConversations() {
    try {
        const response = await fetch("/api/conversations");

        if (response.status === 401) {
            window.location.href = "/login.html";
            return;
        }

        if (!response.ok) {
            throw new Error("Failed to load conversations");
        }

        const data = await response.json();

        chats = data.map(chat => ({
            id: chat.id,
            title: chat.title,
            messages: []
        }));

        renderChatList();

        // if (chats.length > 0) {
        //     activeChatId = chats[0].id;

        //     const messagesResponse = await fetch(
        //         `/api/conversations/${activeChatId}/messages`
        //     );

        //     if (!messagesResponse.ok) {
        //         throw new Error("Failed to load messages");
        //     }

        //     const messages = await messagesResponse.json();
        //     chats[0].messages = messages;

        //     renderChatList();
        //     renderMessages();
        // } else {
        //     await createChat();
        // }
        if (chats.length > 0) {
    activeChatId = chats[0].id;

    const messagesResponse = await fetch(
        `/api/conversations/${activeChatId}/messages`
    );

    if (!messagesResponse.ok) {
        throw new Error("Failed to load messages");
    }

    chats[0].messages = await messagesResponse.json();

    renderChatList();
    renderMessages();
} 
    else {
    activeChatId = null;
    renderChatList();
    renderMessages();
}
    } catch (error) {
        console.error("Error loading recent chats:", error);
        showToast("Couldn't load recent chats. Check the backend.");
    }
}
async function sendMessage() {
    const text = input.value.trim();

    if (!text || isWaiting) return;

    if (!getActiveChat()) {
        createChat();
    }

    const chat = getActiveChat();

    chat.messages.push({
        role: "user",
        content: text
    });

    if (chat.title === "New chat") {
        chat.title = text.length > 32
            ? text.slice(0, 32) + "..."
            : text;
    }

    input.value = "";
    input.style.height = "auto";
    isWaiting = true;
    sendButton.disabled = true;

    renderChatList();
    renderMessages();

    const userMessageCount = chat.messages.length;

    try {
        // const reply = await getGeminiReply(chat.messages);
        const reply = await getGeminiReply(chat);
        chat.messages.push({
            role: "assistant",
            content: reply
        });
    } catch (error) {
        console.error(error);

        // Keep the user's message so they can retry.
        chat.messages.push({
            role: "assistant",
            content: "Gemini couldn't respond. Check the backend terminal, API key, and model ID."
        });
    } finally {
        isWaiting = false;
        sendButton.disabled = !input.value.trim();

        if (activeChatId === chat.id) {
            renderMessages();
        }

        input.focus();
    }
}

chatForm.addEventListener("submit", event => {
    event.preventDefault();
    sendMessage();
});

input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 180) + "px";
    sendButton.disabled = !input.value.trim() || isWaiting;
});

input.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();

        if (!isWaiting && input.value.trim()) {
            sendMessage();
        }
    }
});

document.getElementById("newChat").addEventListener("click", () => {
    if (!isWaiting) createChat();
});

document.querySelectorAll(".suggestion").forEach(button => {
    button.addEventListener("click", () => {
        input.value = button.dataset.prompt || "";
        input.dispatchEvent(new Event("input"));
        sendMessage();
    });
});

document.getElementById("menuButton").addEventListener("click", () => {
    document.getElementById("sidebar").classList.add("open");
});

document.getElementById("closeSidebar").addEventListener("click", () => {
    document.getElementById("sidebar").classList.remove("open");
});

modelSelect.addEventListener("change", () => {
    if (modelSelect.value !== "gemini") {
        showToast("Only Gemini is connected right now.");
        modelSelect.value = "gemini";
    }
});

document.getElementById("settingsButton").addEventListener("click", () => {
    showToast("Settings will be added later.");
});

function showToast(message) {
    toast.textContent = message;
    toast.classList.add("show");

    setTimeout(() => {
        toast.classList.remove("show");
    }, 2500);
}
document.getElementById("logoutButton").addEventListener("click", async () => {
    const response = await fetch("/api/logout", {
        method: "POST"
    });

    if (response.ok) {
        window.location.href = "/login.html";
    } else {
        showToast("Couldn't log out. Try again.");
    }
});
// Start with a fresh conversation.
document.getElementById("newChat").addEventListener("click", () => {
    createChat();
});
loadConversations();