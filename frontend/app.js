/**
 * Music Subscription — Frontend JavaScript
 *
 * Manages backend URL switching between the three architectures
 * (EC2, ECS, API Gateway + Lambda) and provides the shared API call helper.
 */

const BACKENDS = {
    ec2:    "http://<YOUR-EC2-PUBLIC-IP>/api",
    ecs:    "http://<YOUR-ALB-DNS-NAME>/api",
    lambda: "https://<YOUR-API-GATEWAY-ID>.execute-api.us-east-1.amazonaws.com/prod",
};

function getBaseUrl() {
    const select = document.getElementById("backend-select");
    const choice = select ? select.value : "lambda";
    return BACKENDS[choice] || BACKENDS.lambda;
}

/**
 * Generic API call helper.
 * Builds the full URL from the selected backend + path, sends the request,
 * and returns the parsed JSON response.
 */
async function apiCall(path, method, body) {
    const base = getBaseUrl();
    const url = base + path;

    const options = {
        method: method,
        headers: { "Content-Type": "application/json" },
    };

    if (body && (method === "POST" || method === "PUT" || method === "DELETE")) {
        options.body = JSON.stringify(body);
    }

    const resp = await fetch(url, options);
    return resp.json();
}

// Persist backend selection across pages
document.addEventListener("DOMContentLoaded", () => {
    const select = document.getElementById("backend-select");
    if (!select) return;

    const saved = localStorage.getItem("backend");
    if (saved && BACKENDS[saved]) {
        select.value = saved;
    }

    select.addEventListener("change", () => {
        localStorage.setItem("backend", select.value);
    });
});
