"use strict";
const HOST = "com.mahmoudbasuony.buzz";
const heading = document.getElementById("heading");
const status = document.getElementById("status");
const progress = document.getElementById("progress");
const hint = document.getElementById("hint");
const retry = document.getElementById("retry");
let port, timer, videoUrl, jobId;

function fail(message) {
  heading.textContent = "التفريغ ما بدأش";
  status.textContent = message;
  hint.textContent = "افتح Buzz وتأكد من إعداداته، وبعدها جرّب تاني.";
  progress.hidden = true;
  clearInterval(timer);
}

function connect() {
  port = chrome.runtime.connectNative(HOST);
  port.onMessage.addListener((message) => {
    if (!message.ok) {
      fail(message.message || "تعذر الاتصال بـBuzz.");
      return;
    }
    const job = message.job;
    if (!job) return;
    jobId = job.id;
    const states = {
      waiting: ["جارٍ فتح Buzz…", "الفيديو اتبعت. مستني البرنامج يجهّز المهمة."],
      submitting: ["جارٍ تجهيز المهمة…", "بنستخدم الإعدادات المحفوظة في Buzz."],
      queued: ["الفيديو في الانتظار", "Buzz هيبدأ أول ما المهمة اللي قبله تخلص."],
      in_progress: ["التفريغ شغّال", job.stage || "Buzz بيجهّز الصوت أو مستني نتيجة التفريغ."],
      completed: ["النص جاهز ✓", "هتلاقي النص مفتوح في Buzz، ونسخة TXT محفوظة في المستندات."],
      skipped: ["النص جاهز ✓", "تم استخدام النص الموجود وفتحه في Buzz."],
    };
    if (["failed", "canceled", "missing"].includes(job.state)) {
      fail(job.message || "المهمة توقفت. راجع Buzz.");
      retry.hidden = false;
      return;
    }
    const text = states[job.state] || ["التفريغ شغّال", "تقدر تتابع المهمة في Buzz."];
    heading.textContent = text[0];
    status.textContent = text[1];
    if (job.state === "in_progress") progress.value = Math.round((job.progress || 0) * 100);
    if (["completed", "skipped"].includes(job.state)) {
      progress.value = 100;
      hint.textContent = "الضغط على نفس الفيديو تاني بيفتح نفس النتيجة.";
      clearInterval(timer);
    }
  });
  port.onDisconnect.addListener(() => {
    const error = chrome.runtime.lastError;
    if (error) fail("وصلة Buzz غير متاحة. شغّل ملف إعداد الإضافة، وتأكد من تثبيت نسخة Buzz الداعمة لها.");
    clearInterval(timer);
    port = null;
  });
}

async function start(retryJob = false) {
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    const url = new URL(tab?.url || "");
    if (url.protocol !== "https:" || !["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"].includes(url.hostname)) {
      throw new Error("افتح فيديو يوتيوب واضغط أيقونة Buzz من صفحته.");
    }
    videoUrl = url.href;
    if (!port) connect();
    retry.hidden = true;
    progress.hidden = false;
    progress.removeAttribute("value");
    port.postMessage({action: "start", url: videoUrl, retry: retryJob});
    clearInterval(timer);
    timer = setInterval(() => {
      if (jobId && port) port.postMessage({action: "status", id: jobId});
    }, 1200);
  } catch (error) {
    fail(error.message || "افتح فيديو يوتيوب أولًا.");
  }
}
retry.addEventListener("click", () => start(true));
start();
