"use strict";
const HOST = "com.mahmoudbasuony.buzz";
const heading = document.getElementById("heading");
const status = document.getElementById("status");
const progress = document.getElementById("progress");
const hint = document.getElementById("hint");
const retry = document.getElementById("retry");
let port, timer, videoUrl, jobId;

function fail(message) {
  heading.textContent = "تعذّر إكمال التفريغ";
  status.textContent = message;
  hint.textContent = "افتح Buzz وتحقّق من إعداداته، ثم حاول مجددًا.";
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
      waiting: ["جارٍ فتح Buzz…", "أُرسل الفيديو. جارٍ تجهيز مهمة التفريغ."],
      submitting: ["جارٍ تجهيز المهمة…", "تُستخدم الإعدادات المحفوظة في Buzz."],
      queued: ["الفيديو في الانتظار", "سيبدأ التفريغ بعد اكتمال المهام السابقة."],
      in_progress: ["جارٍ التفريغ", job.stage || "جارٍ تجهيز الصوت أو انتظار نتيجة التفريغ."],
      completed: ["النص جاهز ✓", "سيفتح النص في Buzz. حُفظت أيضًا نسخة TXT في مجلد المستندات."],
      skipped: ["النص جاهز ✓", "تم استخدام النص الموجود وفتحه في Buzz."],
    };
    if (["failed", "canceled", "missing"].includes(job.state)) {
      fail(job.message || "توقفت المهمة. راجع التفاصيل في Buzz.");
      retry.hidden = false;
      return;
    }
    const text = states[job.state] || ["جارٍ التفريغ", "يمكنك متابعة المهمة في Buzz."];
    heading.textContent = text[0];
    status.textContent = text[1];
    if (job.state === "in_progress") progress.value = Math.round((job.progress || 0) * 100);
    if (["completed", "skipped"].includes(job.state)) {
      progress.value = 100;
      hint.textContent = "الضغط على الفيديو نفسه مجددًا يفتح النتيجة المحفوظة.";
      clearInterval(timer);
    }
  });
  port.onDisconnect.addListener(() => {
    const error = chrome.runtime.lastError;
    if (error) fail("تعذّر الاتصال بـBuzz. شغّل ملف إعداد الإضافة وتأكد من تثبيت نسخة Buzz الداعمة لها.");
    clearInterval(timer);
    port = null;
  });
}

async function start(retryJob = false) {
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    const url = new URL(tab?.url || "");
    if (url.protocol !== "https:" || !["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"].includes(url.hostname)) {
      throw new Error("افتح صفحة فيديو يوتيوب، ثم اضغط أيقونة Buzz.");
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
