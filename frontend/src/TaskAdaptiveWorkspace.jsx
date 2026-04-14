import React, { useEffect, useRef, useState } from "react";
import "./TaskWorkspace.css";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Settings, Plug, ListTodo, X } from 'lucide-react';

// Task type detection from message - PRIORITY ORDER MATTERS
function detectTaskType(message) {
  if (!message) return null;
  const text = message.toLowerCase();

  // 1. Meeting signals - CHECK FIRST (highest priority for real-world tasks)
  // These are explicit meeting/scheduling requests
  const meetingKeywords = [
    'meeting',
    'create meeting', 'create a meeting', 'create and schedule',
    'schedule a ', 'schedule call', 'set up a call',
    'invite', 'calendar event',
    'zoom call', 'zoom meeting',
    'jitsi',
    'google meet', 'meet call',
    'teams call',
    'book a call', 'arrange a meeting'
  ];
  const hasMeetingSignals = meetingKeywords.some(k => text.includes(k));

  // 2. Trade signals - financial operations need early detection
  const hasTradeSignals = ['trade', 'btc', 'stock', 'crypto', 'usdt', 'sell bitcoin', 'buy bitcoin'].some(k => text.includes(k));

  // 3. Flight/Travel signals
  const hasFlightSignals = ['flight', 'book a flight', 'travel to', 'trip to', 'fly to'].some(k => text.includes(k));

  // 4. Shopping signals
  const hasShoppingSignals = ['shop', 'order', 'add to cart', 'buy a shirt', 'buy shoes', 'purchase'].some(k => text.includes(k)) && !text.includes('btc');

  // 5. Email signals
  const hasEmailSignals = ['send email', 'email to', 'compose email', 'draft email', 'mail to', 'inbox'].some(k => text.includes(k));

  // 6. Video signals
  const hasVideoSignals = ['edit video', 'video edit', 'youtube video', 'create video'].some(k => text.includes(k));

  // 7. Social signals
  const hasSocialSignals = ['post on instagram', 'post on facebook', 'social media', 'tweet', 'linkedin post'].some(k => text.includes(k));

  // 8. Code signals - ONLY trigger for explicit code/development requests
  // Remove generic words like "create" that conflict with other task types
  const codeKeywords = [
    'build me a', 'build an app', 'build a website', 'build a web',
    'build a todo', 'todo app', 'to-do app', 'todo list',
    'local storage',
    'code', 'coding', 'program', 'programming',
    'create a website', 'create an app', 'create a web app', 'create a landing page',
    'generate code', 'write code', 'develop',
    'webapp', 'web app', 'website', 'landing page',
    'frontend', 'backend', 'fullstack',
    'react', 'vue', 'angular', 'next.js', 'vite',
    'html', 'css', 'javascript', 'typescript', 'python app',
    'ecommerce', 'e-commerce', 'online store',
    'ui design', 'ux design', 'design a page'
  ];
  const hasCodeSignals = codeKeywords.some(k => text.includes(k)) || (
    /\b(build|create|make|develop|implement)\b[\s\S]{0,60}\b(app|website|landing page|dashboard|ui|frontend|backend|todo)\b/.test(text)
  );

  // PRIORITY ORDER: Meeting > Trade > Flight > Shopping > Email > Video > Social > Code > Browser
  // Meeting takes priority because "create meeting" should not trigger code workspace
  if (hasMeetingSignals) return 'meeting';
  if (hasTradeSignals) return 'trade';
  if (hasFlightSignals) return 'flight';
  if (hasShoppingSignals) return 'shopping';
  if (hasEmailSignals) return 'email';
  if (hasVideoSignals) return 'video';
  if (hasSocialSignals) return 'social';
  if (hasCodeSignals) return 'code';
  return 'browser';
}

// Task configurations
const TASK_CONFIG = {
  code: { icon: '📄', label: 'Code IDE', badges: [{ cls: 'bp', text: 'IDE' }, { cls: 'bg', text: 'Live' }] },
  meeting: { icon: '📞', label: 'Meeting', badges: [{ cls: 'bp', text: 'Meeting' }, { cls: 'bb', text: 'Jitsi ready' }] },
  trade: { icon: '📈', label: 'Trade', badges: [{ cls: 'br', text: 'High risk' }, { cls: 'bp', text: 'Confirm needed' }] },
  shopping: { icon: '🛍️', label: 'Shopping', badges: [{ cls: 'bg', text: 'Low risk' }] },
  flight: { icon: '✈️', label: 'Travel', badges: [{ cls: 'ba', text: 'Medium risk' }] },
  video: { icon: '🎬', label: 'Video Edit', badges: [{ cls: 'bp', text: 'Editor' }] },
  social: { icon: '📱', label: 'Social', badges: [{ cls: 'bp', text: 'Post' }] },
  email: { icon: '📧', label: 'Email', badges: [{ cls: 'bg', text: 'Send' }] },
  browser: { icon: '🌐', label: 'Browser', badges: [{ cls: 'ba', text: 'Fallback' }] }
};

function extractEmails(text) {
  if (!text) return [];
  const matches = text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi) || [];
  const seen = new Set();
  const out = [];
  for (const m of matches) {
    const email = m.trim();
    const k = email.toLowerCase();
    if (!seen.has(k)) {
      seen.add(k);
      out.push(email);
    }
  }
  return out;
}

// Extract code from AI response - check steps data, markdown, and result
function extractCodeFromResponse(messages) {
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg.role === 'ai') {
      // 1. Check steps for code_exec events
      if (msg.steps && Array.isArray(msg.steps)) {
        for (let j = msg.steps.length - 1; j >= 0; j--) {
          const step = msg.steps[j];
          const stepType = step.event || step.type; // Backend uses 'event', fallback to 'type'
          if (stepType === 'code_exec' && step.data?.code) {
            return { code: step.data.code, language: detectLanguage(step.data.code) };
          }
          // Also check confirm_needed for code
          if (stepType === 'confirm_needed' && step.data?.params?.code) {
            return { code: step.data.params.code, language: detectLanguage(step.data.params.code) };
          }
          if (stepType === 'confirm_needed' && step.data?.code) {
            return { code: step.data.code, language: detectLanguage(step.data.code) };
          }
        }
      }
      
      // 2. Check markdown code blocks in message text
      if (msg.text) {
        const codeBlockMatch = msg.text.match(/```(\w+)?\n([\s\S]*?)```/);
        if (codeBlockMatch) {
          return { code: codeBlockMatch[2], language: codeBlockMatch[1] || 'javascript' };
        }
      }
      
      // 3. Check result object
      if (msg.result?.code) {
        return { code: msg.result.code, language: detectLanguage(msg.result.code) };
      }
    }
  }
  return null;
}

// Detect programming language from code
function detectLanguage(code) {
  if (!code) return 'text';
  if (code.includes('const ') || code.includes('require(') || code.includes('import ') && code.includes('from ')) return 'javascript';
  if (code.includes('def ') || code.includes('import ') || code.includes('from flask')) return 'python';
  if (code.includes('<html') || code.includes('<!DOCTYPE')) return 'html';
  if (code.includes('{') && code.includes(':') && code.includes(';')) return 'css';
  return 'javascript';
}

function defaultPrimaryFilename(language) {
  if (language === 'html') return 'index.html';
  if (language === 'python') return 'app.py';
  if (language === 'css') return 'style.css';
  return 'index.js';
}

function parseFileMapFromText(text) {
  if (!text) return null;
  // Supports patterns like:
  // // filepath: src/App.jsx
  // # filepath: app.py
  // <!-- filepath: index.html -->
  const re = /^(?:\/\/|#|<!--)\s*filepath\s*:\s*([^\s>]+)\s*(?:-->)?\s*$/gmi;
  const matches = Array.from(text.matchAll(re));
  if (matches.length === 0) return null;

  const fileMap = {};
  for (let i = 0; i < matches.length; i++) {
    const name = (matches[i][1] || '').trim();
    const startIdx = matches[i].index + matches[i][0].length;
    const endIdx = (i + 1 < matches.length) ? matches[i + 1].index : text.length;
    const content = text.slice(startIdx, endIdx).replace(/^\s*\n/, '');
    if (name && content.trim()) fileMap[name] = content.trimEnd();
  }

  return Object.keys(fileMap).length ? fileMap : null;
}

function extractCodeArtifacts(messages) {
  // Only consider artifacts produced AFTER the latest user message.
  // This prevents the IDE/Preview from showing the previous task's code
  // when the current response contains no artifacts.
  let lastUserIdx = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i]?.role === 'user') { lastUserIdx = i; break; }
  }
  const startIdx = Math.min(messages.length - 1, lastUserIdx + 1);

  // Try to recover multi-file artifacts first.
  for (let i = messages.length - 1; i >= startIdx; i--) {
    const msg = messages[i];
    if (msg?.role !== 'ai') continue;

    // 1) Steps may contain generated/executed code (sometimes with filepath markers)
    if (Array.isArray(msg.steps)) {
      for (let j = msg.steps.length - 1; j >= 0; j--) {
        const step = msg.steps[j];
        const stepType = step.event || step.type;
        if (stepType === 'code_exec' && step.data?.code) {
          const fm = parseFileMapFromText(step.data.code);
          if (fm) return { files: fm, language: detectLanguage(step.data.code) };
        }
      }
    }

    // 2) Message text: parse filepath blocks or recover from multiple code fences
    if (msg.text) {
      const fm = parseFileMapFromText(msg.text);
      if (fm) return { files: fm, language: detectLanguage(Object.values(fm)[0] || '') };

      const fenceRe = /```(\w+)?\n([\s\S]*?)```/g;
      const fences = Array.from(msg.text.matchAll(fenceRe)).map(m => {
        const lang = (m[1] || '').toLowerCase();
        let content = (m[2] || '').trimEnd();

        // Check if content has filepath marker as first line
        const filepathMatch = content.match(/^(?:\/\/|#|<!--)\s*filepath\s*:\s*([^\s>]+)\s*(?:-->)?\s*\n/i);
        let filename = null;
        if (filepathMatch) {
          filename = filepathMatch[1].trim();
          content = content.slice(filepathMatch[0].length); // Remove the marker line
        }

        return { lang, content, filename };
      })
        .filter(f => f.content.trim())
        // Don't treat shell snippets as files — they are usually install commands.
        .filter(f => !['bash', 'sh', 'shell', 'powershell', 'pwsh', 'zsh'].includes(f.lang));

      // If we have filepath markers, use them
      const filesWithMarkers = fences.filter(f => f.filename);
      if (filesWithMarkers.length > 0) {
        const files = {};
        filesWithMarkers.forEach(f => {
          files[f.filename] = f.content;
        });
        return { files, language: detectLanguage(Object.values(files)[0] || '') };
      }

      // Otherwise, smart mapping by language
      if (fences.length >= 2) {
        const files = {};
        let idx = 1;
        for (const f of fences) {
          if (f.lang === 'html' && !files['index.html']) files['index.html'] = f.content;
          else if (f.lang === 'css' && !files['style.css']) files['style.css'] = f.content;
          else if ((f.lang === 'js' || f.lang === 'javascript') && !files['script.js']) files['script.js'] = f.content;
          else if (f.lang === 'python' && !files['app.py']) files['app.py'] = f.content;
          else {
            const ext = (f.lang === 'js' || f.lang === 'javascript') ? 'js'
              : (f.lang === 'ts' || f.lang === 'typescript') ? 'ts'
                : (f.lang === 'yml' || f.lang === 'yaml') ? 'yml'
                  : (f.lang || 'txt');
            files[`file${idx}.${ext}`] = f.content;
            idx += 1;
          }
        }

        // If we got JS/CSS but no HTML, synthesize a minimal index.html so Preview works.
        if (!files['index.html']) {
          const hasAnyJs = Object.keys(files).some(n => n.toLowerCase().endsWith('.js'));
          const hasAnyCss = Object.keys(files).some(n => n.toLowerCase().endsWith('.css'));
          if (hasAnyJs || hasAnyCss) {
            files['index.html'] = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Preview</title>
  </head>
  <body>
    <div id="app"></div>
  </body>
</html>`;
          }
        }

        return { files, language: detectLanguage(Object.values(files)[0] || '') };
      }
    }

    // 3) Result object
    if (msg.result?.code) {
      const fm = parseFileMapFromText(msg.result.code);
      if (fm) return { files: fm, language: detectLanguage(Object.values(fm)[0] || '') };
    }
  }

  // Fallback: single code blob
  const single = extractCodeFromResponse(messages);
  if (single?.code) {
    const filename = defaultPrimaryFilename(single.language);
    return { files: { [filename]: single.code }, language: single.language };
  }
  return { files: {}, language: 'text' };
}

function buildHtmlSrcDoc(fileMap) {
  if (!fileMap) return null;
  let html = fileMap['index.html'] || fileMap['public/index.html'] || fileMap['src/index.html'];
  if (!html) return null;

  // Clean up the HTML - remove any leading/trailing whitespace
  html = html.trim();

  // Collect all CSS files
  const css = Object.entries(fileMap)
    .filter(([name]) => name.toLowerCase().endsWith('.css'))
    .map(([, content]) => content.trim())
    .join('\n\n');

  // Collect all JS files
  const js = Object.entries(fileMap)
    .filter(([name]) => name.toLowerCase().endsWith('.js'))
    .map(([, content]) => content.trim())
    .join('\n\n');

  let doc = html;

  // Inject CSS
  if (css.trim()) {
    if (doc.includes('</head>')) {
      doc = doc.replace('</head>', `<style>\n${css}\n</style>\n</head>`);
    } else if (doc.includes('<head>')) {
      doc = doc.replace('<head>', `<head>\n<style>\n${css}\n</style>`);
    } else {
      // No head tag, add at the beginning
      doc = `<style>\n${css}\n</style>\n` + doc;
    }
  }

  // Inject JS
  if (js.trim()) {
    if (doc.includes('</body>')) {
      doc = doc.replace('</body>', `<script>\n${js}\n</script>\n</body>`);
    } else if (doc.includes('<body>')) {
      // Find the closing body tag
      const bodyEndIdx = doc.lastIndexOf('</body>');
      if (bodyEndIdx !== -1) {
        doc = doc.slice(0, bodyEndIdx) + `<script>\n${js}\n</script>\n` + doc.slice(bodyEndIdx);
      } else {
        // No closing body, append to end
        doc = doc + `\n<script>\n${js}\n</script>`;
      }
    } else {
      // No body tag, append to end
      doc = doc + `\n<script>\n${js}\n</script>`;
    }
  }

  return doc;
}

// Extract files structure from AI response
function extractFilesFromResponse(messages, codeData) {
  const files = [];
  
  // If we detected language, suggest appropriate files
  if (codeData) {
    if (codeData.language === 'javascript') {
      files.push('server.js', 'package.json');
    } else if (codeData.language === 'python') {
      files.push('app.py', 'requirements.txt');
    } else if (codeData.language === 'html') {
      files.push('index.html', 'style.css');
    }
  }
  
  // Look for explicit file mentions
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg.role === 'ai' && msg.text) {
      const fileMatches = msg.text.match(/(?:create|file|generated?):\s*[`"]?([a-zA-Z0-9_\-./]+\.[a-zA-Z]+)[`"]?/gi);
      if (fileMatches) {
        fileMatches.forEach(m => {
          const name = m.match(/[a-zA-Z0-9_\-./]+\.[a-zA-Z]+/)?.[0];
          if (name && !files.includes(name)) files.push(name);
        });
      }
    }
  }
  
  return files.length > 0 ? files : ['index.js', 'package.json', 'README.md'];
}

// CODE WORKSPACE - uses extracted artifacts for real per-file display and preview
function CodeWorkspace({ taskMessage, messages, artifacts }) {
  const fileNames = Object.keys(artifacts?.files || {});
  const [activeFile, setActiveFile] = useState(fileNames[0] || 'index.js');

  useEffect(() => {
    if (!fileNames.length) return;
    if (!fileNames.includes(activeFile)) setActiveFile(fileNames[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileNames.join('|')]);
  
  // Extract terminal output from steps
  const terminalOutput = [];
  const lastAIMsg = messages.slice().reverse().find(m => m.role === 'ai' && m.steps);
  if (lastAIMsg?.steps) {
    lastAIMsg.steps.forEach(step => {
      const stepEvent = step.event || step.type; // Backend uses 'event', fallback to 'type'
      if (stepEvent === 'code_exec') {
        terminalOutput.push({ type: 'cmd', text: '$ Executing code...' });
        if (step.data?.output) {
          terminalOutput.push({ type: 'info', text: step.data.output });
        }
      } else if (stepEvent === 'action_result' || stepEvent === 'result') {
        const success = step.data?._meta?.success;
        const error = step.data?._meta?.error;
        if (success) {
          terminalOutput.push({ type: 'ok', text: `✔ ${step.content || 'Success'}` });
        } else if (error) {
          terminalOutput.push({ type: 'err', text: `✗ ${error}` });
        } else if (step.content) {
          terminalOutput.push({ type: 'info', text: step.content });
        }
      }
    });
  }
  
  const code = (artifacts?.files && activeFile && artifacts.files[activeFile])
    ? artifacts.files[activeFile]
    : `// Waiting for AI to generate code...\n// Ask me to build something specific!`;
  const language = artifacts?.language || detectLanguage(code);
  const srcDoc = buildHtmlSrcDoc(artifacts?.files || {});
  
  return (
    <div className="panels">
      {/* File Tree */}
      <div className="panel" style={{width: '140px'}}>
        <div className="panel-header"><span className="ph-icon">📁</span><span className="ph-title">Files</span></div>
        <div className="panel-body">
          <div className="ftree-folder">📁 src/</div>
          {fileNames.length ? fileNames.map(f => (
            <div key={f} className={`ftree-item ${activeFile === f ? 'on' : ''}`} onClick={() => setActiveFile(f)}>
              📄 {f}
            </div>
          )) : (
            <div style={{padding: '8px 10px', fontSize: '10px', color: '#8b949e'}}>
              No files yet
            </div>
          )}
        </div>
      </div>
      
      {/* Editor + Terminal */}
      <div className="panel" style={{flex: 1, minWidth: 0}}>
        <div className="panel-header">
          <span className="ph-icon">✏️</span>
          <span className="ph-title">{activeFile}</span>
          <span className="badge bp" style={{fontSize: '8px'}}>{fileNames.length ? 'AI Generated' : 'Waiting'}</span>
          <span className="badge bg" style={{fontSize: '8px', marginLeft: '4px'}}>{language}</span>
        </div>
        <div className="panel-body" style={{display: 'flex', flexDirection: 'column'}}>
          <div className="code-editor" style={{flex: 1, fontFamily: 'monospace', fontSize: '11px', lineHeight: 1.7, padding: '12px', whiteSpace: 'pre-wrap', wordBreak: 'break-word', overflow: 'auto', maxHeight: '300px'}}>
            {code}
          </div>
          <div className="term" style={{borderTop: '0.5px solid #30363d', padding: '8px 12px', background: '#010409', fontFamily: 'monospace', fontSize: '10px', minHeight: '80px', maxHeight: '120px', overflow: 'auto'}}>
            {terminalOutput.length > 0 ? (
              terminalOutput.map((line, i) => (
                <div key={i}>
                  <span className={line.type === 'ok' ? 'tok' : line.type === 'err' ? 'terr' : line.type === 'cmd' ? 'tc' : 'tp2'}>
                    {line.text}
                  </span>
                </div>
              ))
            ) : (
              <>
                <div><span className="tp2">$ </span><span className="tc">Ready for execution</span></div>
                <div><span className="tp2">$ </span><span className="tcur"></span></div>
              </>
            )}
          </div>
        </div>
      </div>
      
      {/* Live Preview - Show based on language */}
      <div className="panel" style={{flex: 1, minWidth: 0}}>
        <div className="panel-header">
          <span className="ph-icon">👁️</span>
          <span className="ph-title">Preview</span>
          <div style={{display: 'flex', alignItems: 'center', gap: '3px', marginLeft: 'auto'}}>
            <div className={srcDoc ? "ldot" : "ldot-off"}></div>
            <span style={{fontSize: '8px', color: srcDoc ? '#3fb950' : '#8b949e'}}>{srcDoc ? 'ready' : 'waiting'}</span>
          </div>
        </div>
        <div className="panel-body">
          {srcDoc ? (
            <iframe
              title="preview"
              sandbox="allow-scripts allow-forms allow-modals allow-popups"
              style={{width: '100%', height: '100%', border: 'none', background: '#0d1117'}}
              srcDoc={srcDoc}
            />
          ) : fileNames.length ? (
            <div style={{padding: '16px', height: '100%', display: 'flex', flexDirection: 'column', gap: '10px'}}>
              <div style={{background: '#161b22', border: '0.5px solid #30363d', borderRadius: '8px', padding: '12px'}}>
                <div style={{fontSize: '10px', color: '#8b949e', marginBottom: '6px'}}>Preview</div>
                <div style={{fontSize: '11px', color: '#e6edf3'}}>Live preview is available when an `index.html` is generated.</div>
                <div style={{fontSize: '10px', color: '#8b949e', marginTop: '6px'}}>Detected language: {language}</div>
              </div>
            </div>
          ) : (
            <div style={{display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#8b949e', fontSize: '11px', flexDirection: 'column', gap: '8px'}}>
              <div style={{fontSize: '24px'}}>💻</div>
              <div>Ask AI to generate code</div>
              <div style={{fontSize: '10px', color: '#484f58'}}>e.g., "build a todo app" or "create a REST API"</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Parse time from user message
function parseTimeFromMessage(message) {
  if (!message) return null;
  const text = message.toLowerCase();

  // 24h formats: 14:30, 9:05, 14.30
  const m24 = text.match(/\b([01]?\d|2[0-3])[:.](\d{2})\b/);
  if (m24) {
    const hour = parseInt(m24[1], 10);
    const minutes = m24[2];
    const displayHour = hour > 12 ? hour - 12 : (hour === 0 ? 12 : hour);
    const displayAmPm = hour >= 12 ? 'PM' : 'AM';
    return `${displayHour}:${minutes} ${displayAmPm}`;
  }

  // 12h formats: 2pm, 2 pm, at2pm, at 2:30pm, around 2.30 pm
  const m12 = text.match(/(?:\bat\s*|\baround\s*|\bby\s*)?(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b/);
  if (m12) {
    let hour = parseInt(m12[1], 10);
    const minutes = m12[2] ? m12[2] : '00';
    const ampm = (m12[3] || '').replace(/\./g, '');
    if (ampm === 'pm' && hour < 12) hour += 12;
    if (ampm === 'am' && hour === 12) hour = 0;
    const displayHour = hour > 12 ? hour - 12 : (hour === 0 ? 12 : hour);
    const displayAmPm = hour >= 12 ? 'PM' : 'AM';
    return `${displayHour}:${minutes} ${displayAmPm}`;
  }

  // Named time periods
  if (text.includes('morning')) return '9:00 AM';
  if (text.includes('noon') || text.includes('lunch')) return '12:00 PM';
  if (text.includes('afternoon')) return '2:00 PM';
  if (text.includes('evening')) return '5:00 PM';

  return null;
}

// MEETING WORKSPACE - Interactive with backend-backed confirm button
function MeetingWorkspace({ taskMessage, userId, onOpenIntegrations }) {
  const parsedTime = parseTimeFromMessage(taskMessage);
  const detectedEmails = extractEmails(taskMessage);
  const [selectedSlot, setSelectedSlot] = useState(parsedTime || '10:00 AM');
  const [selectedPlatform, setSelectedPlatform] = useState('Jitsi');
  const [attendeeEmail, setAttendeeEmail] = useState(detectedEmails[0] || '');
  const [isCreating, setIsCreating] = useState(false);
  const [meetingLink, setMeetingLink] = useState(null);
  const [error, setError] = useState(null);
  // Track which integrations are connected
  const [integrationStatus, setIntegrationStatus] = useState({
    zoom: false,
    google_meet: false,
    jitsi: true, // Always available (no auth needed)
  });
  const [loadingIntegrations, setLoadingIntegrations] = useState(true);

  const slots = ['9:00 AM', '10:00 AM', '11:00 AM', '12:00 PM', '2:00 PM', '3:00 PM', '4:00 PM', '5:00 PM'];
  const takenSlots = ['9:00 AM', '3:00 PM'];

  const inferredDay = (taskMessage || '').toLowerCase().includes('today') ? 'today' : 'tomorrow';

  function inferPlatformFromMessage(msg) {
    const t = (msg || '').toLowerCase();
    if (t.includes('zoom')) return 'Zoom';
    if (t.includes('google meet') || (t.includes('meet') && !t.includes('meeting minutes'))) return 'Meet';
    if (t.includes('jitsi')) return 'Jitsi';
    return null;
  }

  function slotToISO(slotLabel, dayWord) {
    // slotLabel: "2:00 PM"; dayWord: "today" | "tomorrow"
    const m = String(slotLabel || '').match(/^(\d{1,2})(?::(\d{2}))?\s*(AM|PM)$/i);
    if (!m) return null;
    let hour = parseInt(m[1], 10);
    const minute = parseInt(m[2] || '0', 10);
    const ampm = (m[3] || '').toUpperCase();
    if (ampm === 'PM' && hour < 12) hour += 12;
    if (ampm === 'AM' && hour === 12) hour = 0;

    const d = new Date();
    if (dayWord === 'tomorrow') d.setDate(d.getDate() + 1);
    d.setHours(hour, minute, 0, 0);
    return d.toISOString();
  }

  // Check integration status on mount
  React.useEffect(() => {
    const checkIntegrations = async () => {
      try {
        const res = await fetch(`/api/integrations/?user_id=${encodeURIComponent(userId || 'default')}`);
        if (res.ok) {
          const data = await res.json();
          const connectedServices = (data.connected || []).map(c => c.service?.toLowerCase() || '');
          setIntegrationStatus({
            zoom: connectedServices.includes('zoom'),
            google_meet: connectedServices.includes('google_calendar') || connectedServices.includes('google_meet'),
            jitsi: true,
          });
        }
      } catch (err) {
        console.error('Failed to check integrations:', err);
      } finally {
        setLoadingIntegrations(false);
      }
    };
    checkIntegrations();
  }, [userId]);

  // Auto-select platform from the user's message (only if user hasn't picked one yet)
  React.useEffect(() => {
    const inferred = inferPlatformFromMessage(taskMessage);
    if (!inferred) return;
    setSelectedPlatform((prev) => {
      // Only auto-set when still on the default.
      if (prev === 'Jitsi') return inferred;
      return prev;
    });
  }, [taskMessage]);

  // Update selected slot when task message changes (user specifies time)
  React.useEffect(() => {
    const newTime = parseTimeFromMessage(taskMessage);
    if (newTime) {
      // Find closest matching slot or add custom time
      const matchingSlot = slots.find(s => s.toLowerCase() === newTime.toLowerCase());
      if (matchingSlot) {
        setSelectedSlot(matchingSlot);
      } else {
        setSelectedSlot(newTime);
      }
    }
  }, [taskMessage]);

  const handleConfirmMeeting = async () => {
    setError(null);
    setMeetingLink(null);

    const participants = attendeeEmail?.trim() ? [attendeeEmail.trim()] : detectedEmails;
    if (!participants.length) {
      setError('Add at least one attendee email to send an invite.');
      return;
    }

    // Determine meeting type to use.
    // IMPORTANT: do NOT silently fall back when user explicitly chose Zoom/Meet.
    const platformKey = selectedPlatform === 'Zoom' ? 'zoom' : selectedPlatform === 'Meet' ? 'google_meet' : 'jitsi';
    const isConnected = integrationStatus[platformKey] || selectedPlatform === 'Jitsi';
    if (!isConnected && selectedPlatform !== 'Jitsi') {
      setError(`${selectedPlatform} is not connected. Connect it to create a real ${selectedPlatform} meeting, or choose Jitsi.`);
      if (typeof onOpenIntegrations === 'function') onOpenIntegrations();
      return;
    }
    const meeting_type = platformKey;
    const when = slotToISO(selectedSlot, inferredDay) || `${inferredDay} ${selectedSlot}`;

    setIsCreating(true);
    try {
      const params = new URLSearchParams({
        user_id: userId || 'default',
        title: 'Meeting',
        participants: participants.join(','),
        when,
        meeting_type,
      });
      const res = await fetch(`/api/automation/quick/meeting?${params.toString()}`, { method: 'POST' });
      const data = await res.json();
      if (data?.status === 'integration_required') {
        setError(`Integration required: ${data?.required_integration || meeting_type}. Please connect it to continue.`);
        if (typeof onOpenIntegrations === 'function') onOpenIntegrations();
        return;
      }
      if (!res.ok || data?.status === 'failed') {
        setError(data?.error || data?.message || 'Failed to create meeting');
        return;
      }
      if (data?.meeting_url) {
        setMeetingLink(data.meeting_url);
      } else {
        setError('Meeting created but no meeting_url returned.');
      }
    } catch (err) {
      setError(err?.message || 'Network error');
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="panels">
      <div className="panel" style={{flex: 1}}>
        <div className="panel-header"><span className="ph-icon">📅</span><span className="ph-title">Time slots — tomorrow</span></div>
        <div className="panel-body">
          <div className="slot-grid" style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '4px', padding: '10px 12px'}}>
            {slots.map(s => (
              <div key={s}
                className={`slot ${takenSlots.includes(s) ? 'gone' : ''} ${selectedSlot === s ? 'sel' : ''}`}
                onClick={() => !takenSlots.includes(s) && setSelectedSlot(s)}
                style={{padding: '6px', borderRadius: '5px', border: '0.5px solid #30363d', fontSize: '10px', cursor: takenSlots.includes(s) ? 'default' : 'pointer', textAlign: 'center', color: '#c9d1d9', textDecoration: takenSlots.includes(s) ? 'line-through' : 'none', background: selectedSlot === s ? '#7c3aed22' : 'transparent', borderColor: selectedSlot === s ? '#7c3aed' : '#30363d'}}>
                {s}
              </div>
            ))}
          </div>
          <div className="divider"></div>
          <div className="c-section">Attendees</div>
          <div style={{padding: '6px 12px'}}>
            <input
              type="email"
              placeholder="Add attendee email..."
              value={attendeeEmail}
              onChange={(e) => setAttendeeEmail(e.target.value)}
              style={{width: '100%', background: '#21262d', border: '0.5px solid #30363d', borderRadius: '4px', padding: '6px 8px', fontSize: '10px', color: '#e6edf3', outline: 'none', marginBottom: '8px'}}
            />
          </div>
          <div className="attendee" style={{display: 'flex', alignItems: 'center', gap: '7px', padding: '6px 12px', borderBottom: '0.5px solid #21262d'}}>
            <div style={{width: '22px', height: '22px', borderRadius: '50%', background: '#7c3aed44', color: '#d2a8ff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '9px', fontWeight: 500}}>YO</div>
            <div><div style={{fontSize: '10px', color: '#c9d1d9'}}>You</div><div style={{fontSize: '9px', color: '#3fb950'}}>● Available</div></div>
          </div>
          {attendeeEmail && (
            <div className="attendee" style={{display: 'flex', alignItems: 'center', gap: '7px', padding: '6px 12px', borderBottom: '0.5px solid #21262d'}}>
              <div style={{width: '22px', height: '22px', borderRadius: '50%', background: '#1f6feb44', color: '#58a6ff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '9px', fontWeight: 500}}>
                {attendeeEmail.slice(0, 2).toUpperCase()}
              </div>
              <div><div style={{fontSize: '10px', color: '#c9d1d9'}}>{attendeeEmail}</div><div style={{fontSize: '9px', color: '#8b949e'}}>Pending invite</div></div>
            </div>
          )}
          <div className="c-section" style={{marginTop: '6px'}}>Platform</div>
          <div style={{display: 'flex', gap: '5px', padding: '6px 12px'}}>
            {[
              { key: 'Jitsi', label: 'Jitsi', connected: true },
              { key: 'Zoom', label: 'Zoom', connected: integrationStatus.zoom },
              { key: 'Meet', label: 'Meet', connected: integrationStatus.google_meet },
            ].map(p => (
              <div key={p.key} className={`slot ${selectedPlatform === p.key ? 'sel' : ''}`}
                onClick={() => setSelectedPlatform(p.key)}
                style={{
                  flex: 1,
                  padding: '6px',
                  borderRadius: '5px',
                  border: '0.5px solid #30363d',
                  fontSize: '10px',
                  cursor: 'pointer',
                  textAlign: 'center',
                  background: selectedPlatform === p.key ? '#7c3aed22' : 'transparent',
                  borderColor: selectedPlatform === p.key ? '#7c3aed' : p.connected ? '#30363d' : '#f8514955',
                  color: selectedPlatform === p.key ? '#d2a8ff' : '#c9d1d9',
                  position: 'relative',
                }}>
                {p.label}
                {!p.connected && (
                  <span style={{fontSize: '7px', color: '#f85149', display: 'block', marginTop: '2px'}}>
                    Not connected
                  </span>
                )}
                {p.connected && p.key !== 'Jitsi' && (
                  <span style={{fontSize: '7px', color: '#3fb950', display: 'block', marginTop: '2px'}}>
                    ● Connected
                  </span>
                )}
              </div>
            ))}
          </div>

          {/* Warning for unconnected platform */}
          {selectedPlatform !== 'Jitsi' && !integrationStatus[selectedPlatform === 'Zoom' ? 'zoom' : 'google_meet'] && (
            <div style={{margin: '6px 12px', padding: '8px', background: '#f8514911', border: '0.5px solid #f85149', borderRadius: '6px', color: '#f85149'}}>
              <div style={{fontSize: '10px'}}>
                ⚠️ {selectedPlatform} is not connected. Connect it to create a real {selectedPlatform} meeting, or choose Jitsi.
                <a
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    if (typeof onOpenIntegrations === 'function') onOpenIntegrations();
                  }}
                  style={{color: '#58a6ff', marginLeft: '4px', textDecoration: 'underline'}}
                >
                  Connect {selectedPlatform}
                </a>
              </div>
            </div>
          )}

          {error && (
            <div style={{margin: '10px 12px', padding: '10px', background: '#f8514911', border: '0.5px solid #f85149', borderRadius: '7px', color: '#f85149'}}>
              <div style={{fontSize: '10px', fontWeight: 500, marginBottom: '4px'}}>✗ Couldn’t create meeting</div>
              <div style={{fontSize: '10px'}}>{error}</div>
            </div>
          )}

          {meetingLink ? (
            <div style={{margin: '10px 12px', padding: '10px', background: '#238636', borderRadius: '7px', color: '#fff'}}>
              <div style={{fontSize: '10px', fontWeight: 500, marginBottom: '4px'}}>✓ Meeting Created!</div>
              <a href={meetingLink} target="_blank" rel="noopener noreferrer" style={{fontSize: '10px', color: '#fff', wordBreak: 'break-all'}}>
                {meetingLink}
              </a>
            </div>
          ) : (
            <button
              className="cfm-btn"
              onClick={handleConfirmMeeting}
              disabled={isCreating || loadingIntegrations}
              style={{margin: '10px 12px', padding: '7px', background: (isCreating || loadingIntegrations) ? '#484f58' : '#7c3aed', border: 'none', borderRadius: '7px', color: '#fff', fontSize: '10px', cursor: (isCreating || loadingIntegrations) ? 'not-allowed' : 'pointer', display: 'block', width: 'calc(100% - 24px)'}}>
              {isCreating ? 'Creating...' : loadingIntegrations ? 'Loading integration status...' : 'Confirm & send invites'}
            </button>
          )}
        </div>
      </div>
      <div className="panel" style={{flex: 1}}>
        <div className="panel-header">
          <span className="ph-icon">📹</span><span className="ph-title">Live meeting preview</span>
          <div style={{display: 'flex', alignItems: 'center', gap: '3px', marginLeft: 'auto'}}><div className={meetingLink ? 'ldot' : 'ldot-off'}></div><span style={{fontSize: '8px', color: meetingLink ? '#3fb950' : '#8b949e'}}>{selectedPlatform}</span></div>
        </div>
        <div className="panel-body">
          <div className="cam-grid" style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px', padding: '10px'}}>
            <div className="cam" style={{background: '#21262d', borderRadius: '8px', height: '72px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: '3px', position: 'relative', border: '0.5px solid #30363d'}}>
              <div style={{position: 'absolute', top: '4px', left: '4px', background: '#f85149', color: '#fff', fontSize: '7px', padding: '1px 4px', borderRadius: '3px'}}>LIVE</div>
              <span style={{fontSize: '18px'}}>👤</span>
              <div style={{fontSize: '9px', color: '#8b949e'}}>You</div>
            </div>
            <div className="cam" style={{background: '#21262d', borderRadius: '8px', height: '72px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: '3px', border: '0.5px solid #30363d'}}>
              <span style={{fontSize: '18px'}}>👤</span>
              <div style={{fontSize: '9px', color: '#8b949e'}}>{attendeeEmail || 'Guest'}</div>
            </div>
          </div>
          <div className="meet-controls" style={{display: 'flex', justifyContent: 'center', gap: '8px', padding: '8px'}}>
            <div className="mc" style={{width: '26px', height: '26px', borderRadius: '50%', background: '#21262d', border: '0.5px solid #30363d', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '11px', cursor: 'pointer'}}>🎤</div>
            <div className="mc" style={{width: '26px', height: '26px', borderRadius: '50%', background: '#21262d', border: '0.5px solid #30363d', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '11px', cursor: 'pointer'}}>📹</div>
            <div className="mc" style={{width: '26px', height: '26px', borderRadius: '50%', background: '#3fb950', border: '0.5px solid #3fb950', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '11px', cursor: 'pointer'}}>📞</div>
            <div className="mc" style={{width: '26px', height: '26px', borderRadius: '50%', background: '#f85149', border: '0.5px solid #f85149', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '11px', cursor: 'pointer'}}>⬇</div>
          </div>

          {meetingLink && (
            <div style={{padding: '8px 12px', textAlign: 'center'}}>
              <div style={{fontSize: '10px', color: '#3fb950', marginBottom: '8px'}}>Meeting ready at {selectedSlot}</div>
              <a
                href={meetingLink}
                target="_blank"
                rel="noopener noreferrer"
                style={{display: 'inline-block', padding: '8px 16px', background: '#7c3aed', color: '#fff', borderRadius: '6px', fontSize: '11px', textDecoration: 'none', fontWeight: 500}}
              >
                Join Now →
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// TRADE WORKSPACE
function TradeWorkspace({ taskMessage }) {
  const [side, setSide] = useState('buy');
  const bars = [35, 42, 38, 55, 48, 62, 58, 45, 52, 68, 55, 48];
  
  return (
    <div className="panels">
      <div className="panel" style={{flex: 1}}>
        <div className="panel-header"><span className="ph-icon">📈</span><span className="ph-title">BTC/USDT live</span></div>
        <div className="panel-body">
          <div className="chart-bars" style={{display: 'flex', alignItems: 'flex-end', gap: '1px', height: '50px', padding: '0 12px', marginTop: '6px'}}>
            {bars.map((h, i) => (
              <div key={i} className={`bar ${i % 2 === 0 ? 'bar-up' : 'bar-dn'}`} style={{flex: 1, height: `${h}%`, borderRadius: '1px 1px 0 0', background: i % 2 === 0 ? '#3fb950' : '#f85149'}}></div>
            ))}
          </div>
          <div className="price-big" style={{fontSize: '20px', color: '#e6edf3', fontWeight: 500, padding: '0 12px', marginTop: '6px'}}>$67,420</div>
          <div className="price-chg" style={{fontSize: '10px', padding: '0 12px 8px', color: '#3fb950'}}>+2.4% (24h)</div>
          <div className="order-row" style={{display: 'flex', gap: '5px', padding: '10px 12px'}}>
            <div className={`order-side ${side === 'buy' ? 'buy-side' : ''}`} 
              onClick={() => setSide('buy')}
              style={{flex: 1, padding: '6px', borderRadius: '6px', textAlign: 'center', fontSize: '10px', cursor: 'pointer', border: '0.5px solid', background: side === 'buy' ? '#23863622' : '#21262d', borderColor: side === 'buy' ? '#238636' : '#30363d', color: side === 'buy' ? '#3fb950' : '#8b949e'}}>
              Buy
            </div>
            <div className={`order-side ${side === 'sell' ? 'sell-side' : ''}`}
              onClick={() => setSide('sell')}
              style={{flex: 1, padding: '6px', borderRadius: '6px', textAlign: 'center', fontSize: '10px', cursor: 'pointer', border: '0.5px solid', background: side === 'sell' ? '#f8514922' : '#21262d', borderColor: side === 'sell' ? '#f85149' : '#30363d', color: side === 'sell' ? '#f85149' : '#8b949e'}}>
              Sell
            </div>
          </div>
          <div className="confirm-wrap" style={{margin: '0 12px 10px', background: '#f8514911', border: '0.5px solid #f85149', borderRadius: '8px', padding: '9px 10px'}}>
            <div className="cw-title" style={{fontSize: '11px', color: '#f85149', fontWeight: 500, marginBottom: '6px'}}>⚠️ High risk trade - Confirm required</div>
            <div className="cw-row" style={{display: 'flex', justifyContent: 'space-between', marginBottom: '3px'}}>
              <span className="cw-k" style={{fontSize: '9px', color: '#8b949e'}}>Amount:</span>
              <span className="cw-v" style={{fontSize: '9px', color: '#e6edf3'}}>0.1 BTC</span>
            </div>
            <div className="cw-row" style={{display: 'flex', justifyContent: 'space-between', marginBottom: '3px'}}>
              <span className="cw-k" style={{fontSize: '9px', color: '#8b949e'}}>Price:</span>
              <span className="cw-v" style={{fontSize: '9px', color: '#e6edf3'}}>$6,742</span>
            </div>
            <div className="cw-btns" style={{display: 'flex', gap: '5px', marginTop: '7px'}}>
              <button className="cw-go" style={{flex: 1, padding: '6px', borderRadius: '6px', fontSize: '10px', cursor: 'pointer', border: '0.5px solid #f85149', background: '#f85149', color: '#fff'}}>Confirm Trade</button>
              <button className="cw-no" style={{flex: 1, padding: '6px', borderRadius: '6px', fontSize: '10px', cursor: 'pointer', border: '0.5px solid #30363d', background: 'transparent', color: '#8b949e'}}>Cancel</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// SHOPPING WORKSPACE
function ShoppingWorkspace({ taskMessage }) {
  const products = [
    { name: 'Nike Dri-FIT Shirt', site: 'Amazon', price: '₹1,299', best: true },
    { name: 'Adidas Originals', site: 'Flipkart', price: '₹1,499', best: false },
    { name: 'Puma Essential', site: 'Myntra', price: '₹999', best: false }
  ];
  
  return (
    <div className="panels">
      <div className="panel" style={{flex: 1}}>
        <div className="panel-header"><span className="ph-icon">🛍️</span><span className="ph-title">Best matches</span></div>
        <div className="panel-body">
          {products.map((p, i) => (
            <div key={i} className={`prod-card ${p.best ? 'best' : ''}`} style={{background: '#0d1117', border: '0.5px solid', borderColor: p.best ? '#3fb950' : '#30363d', borderRadius: '7px', margin: '6px 12px', padding: '9px', cursor: 'pointer'}}>
              <div className="prod-top" style={{display: 'flex', alignItems: 'center', gap: '8px'}}>
                <div className="prod-img" style={{fontSize: '22px'}}>👕</div>
                <div><div className="prod-name" style={{fontSize: '10px', color: '#c9d1d9', fontWeight: 500}}>{p.name}</div><div className="prod-site" style={{fontSize: '9px', color: '#8b949e'}}>{p.site}</div></div>
                <div className="prod-price" style={{fontSize: '12px', color: '#e6edf3', fontWeight: 500, marginLeft: 'auto'}}>{p.price}</div>
              </div>
              {p.best && <div className="prod-tag tg" style={{fontSize: '8px', marginTop: '4px', color: '#3fb950'}}>✓ Best match</div>}
            </div>
          ))}
          <div className="checkout-block" style={{margin: '6px 12px 10px', background: '#161b22', border: '0.5px solid #30363d', borderRadius: '8px', padding: '10px'}}>
            <div className="checkout-row" style={{display: 'flex', justifyContent: 'space-between', marginBottom: '4px'}}>
              <span className="ck-k" style={{fontSize: '9px', color: '#8b949e'}}>Selected:</span>
              <span className="ck-v" style={{fontSize: '9px', color: '#c9d1d9'}}>Nike Dri-FIT Shirt</span>
            </div>
            <div className="checkout-row" style={{display: 'flex', justifyContent: 'space-between', marginBottom: '4px'}}>
              <span className="ck-k" style={{fontSize: '9px', color: '#8b949e'}}>Total:</span>
              <span className="ck-v" style={{fontSize: '9px', color: '#c9d1d9'}}>₹1,299</span>
            </div>
            <button className="order-btn" style={{width: '100%', marginTop: '8px', padding: '7px', background: '#3fb950', border: 'none', borderRadius: '7px', color: '#fff', fontSize: '10px', cursor: 'pointer'}}>Place Order</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// BROWSER FALLBACK WORKSPACE
function BrowserWorkspace({ taskMessage, messages }) {
  const lastAIMsg = messages?.slice?.().reverse().find(m => m.role === 'ai' && Array.isArray(m.steps) && m.steps.length > 0);
  const rawSteps = Array.isArray(lastAIMsg?.steps) ? lastAIMsg.steps : [];

  const steps = rawSteps
    .map((s) => {
      const event = s.event || s.type || 'step';
      const text = s.content || s.message || event;
      const meta = s.data?._meta;
      const ok = meta?.success === true;
      const err = meta?.success === false || !!meta?.error;
      return { event, text, ok, err };
    })
    .slice(-12);

  const urlCandidate = rawSteps
    .map(s => s?.data?.params?.url || s?.data?.url)
    .find(Boolean);
  
  return (
    <div className="panels">
      <div className="panel" style={{flex: 1}}>
        <div className="panel-header">
          <span className="ph-icon">🌐</span><span className="ph-title">Browser Automation</span>
          <span className="badge ba" style={{marginLeft: 'auto'}}>Fallback mode</span>
        </div>
        <div className="panel-body">
          <div className="browser-bar-2" style={{height: '26px', background: '#0d1117', borderBottom: '0.5px solid #30363d', display: 'flex', alignItems: 'center', padding: '0 8px', gap: '5px'}}>
            <div className="bdots2" style={{display: 'flex', gap: '3px'}}>
              <span style={{width: '6px', height: '6px', borderRadius: '50%', background: '#f85149'}}></span>
              <span style={{width: '6px', height: '6px', borderRadius: '50%', background: '#d29922'}}></span>
              <span style={{width: '6px', height: '6px', borderRadius: '50%', background: '#3fb950'}}></span>
            </div>
            <div className="burl2" style={{flex: 1, background: '#21262d', borderRadius: '3px', padding: '2px 7px', fontSize: '9px', color: '#8b949e', fontFamily: 'monospace'}}>
              {urlCandidate || '(waiting for a real browser action)'}
            </div>
            <div className="ai-badge2" style={{fontSize: '8px', background: '#7c3aed', color: '#fff', padding: '1px 5px', borderRadius: '3px'}}>AI</div>
          </div>
          <div className="steps-list" style={{padding: '12px', display: 'flex', flexDirection: 'column', gap: '8px'}}>
            {steps.length ? steps.map((s, i) => (
              <div key={i} className="sl-step" style={{display: 'flex', alignItems: 'center', gap: '7px', fontSize: '10px', color: '#8b949e'}}>
                <div style={{
                  width: '16px', height: '16px', borderRadius: '50%', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '8px',
                  background: s.ok ? '#23863622' : s.err ? '#f8514922' : '#21262d',
                  border: `0.5px solid ${s.ok ? '#238636' : s.err ? '#f85149' : '#30363d'}`,
                  color: s.ok ? '#3fb950' : s.err ? '#f85149' : '#8b949e'
                }}>
                  {s.ok ? '✓' : s.err ? '!' : '●'}
                </div>
                <span style={{color: s.ok ? '#3fb950' : s.err ? '#f85149' : '#8b949e'}}>{s.text}</span>
              </div>
            )) : (
              <>
                <div style={{fontSize: '10px', color: '#8b949e'}}>
                  No browser automation has run for this task yet.
                </div>
                <div style={{fontSize: '10px', color: '#484f58'}}>
                  If you expected automation, ask the agent to “open the site and perform the steps”, and you’ll see real tool steps here.
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// VIDEO WORKSPACE
function VideoWorkspace({ taskMessage }) {
  return (
    <div className="panels">
      <div className="panel" style={{flex: 1}}>
        <div className="panel-header"><span className="ph-icon">🎬</span><span className="ph-title">Video Editor</span></div>
        <div className="panel-body">
          <div className="video-screen" style={{background: '#000', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: '6px', padding: '16px', minHeight: '120px', borderBottom: '0.5px solid #30363d'}}>
            <span style={{fontSize: '32px'}}>🎬</span>
            <span style={{fontSize: '10px', color: '#8b949e'}}>product_video.mp4</span>
            <span style={{fontSize: '9px', color: '#3fb950'}}>00:00 / 02:45</span>
          </div>
          <div className="tl-wrap" style={{padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: '4px'}}>
            <div className="tl-track" style={{display: 'flex', alignItems: 'center', gap: '6px'}}>
              <span className="tl-lbl" style={{fontSize: '9px', color: '#484f58', minWidth: '38px'}}>Video</span>
              <div className="tl-clips" style={{display: 'flex', gap: '2px', flex: 1}}>
                <div className="clip clip-v" style={{height: '18px', borderRadius: '3px', padding: '0 5px', fontSize: '8px', color: '#fff', display: 'flex', alignItems: 'center', background: '#3a1a6e', flex: 2}}>Intro</div>
                <div className="clip clip-v" style={{height: '18px', borderRadius: '3px', padding: '0 5px', fontSize: '8px', color: '#fff', display: 'flex', alignItems: 'center', background: '#3a1a6e', flex: 3}}>Main</div>
                <div className="clip clip-v" style={{height: '18px', borderRadius: '3px', padding: '0 5px', fontSize: '8px', color: '#fff', display: 'flex', alignItems: 'center', background: '#3a1a6e', flex: 1}}>End</div>
              </div>
            </div>
            <div className="tl-track" style={{display: 'flex', alignItems: 'center', gap: '6px'}}>
              <span className="tl-lbl" style={{fontSize: '9px', color: '#484f58', minWidth: '38px'}}>Audio</span>
              <div className="tl-clips" style={{display: 'flex', gap: '2px', flex: 1}}>
                <div className="clip clip-a" style={{height: '18px', borderRadius: '3px', padding: '0 5px', fontSize: '8px', color: '#fff', display: 'flex', alignItems: 'center', background: '#1a3a1a', flex: 1}}>BG Music</div>
              </div>
            </div>
            <div className="tl-track" style={{display: 'flex', alignItems: 'center', gap: '6px'}}>
              <span className="tl-lbl" style={{fontSize: '9px', color: '#484f58', minWidth: '38px'}}>Text</span>
              <div className="tl-clips" style={{display: 'flex', gap: '2px', flex: 1}}>
                <div className="clip clip-t" style={{height: '18px', borderRadius: '3px', padding: '0 5px', fontSize: '8px', color: '#fff', display: 'flex', alignItems: 'center', background: '#7c3aed', flex: 1}}>Title</div>
                <div className="clip clip-t" style={{height: '18px', borderRadius: '3px', padding: '0 5px', fontSize: '8px', color: '#fff', display: 'flex', alignItems: 'center', background: '#7c3aed', flex: 1}}>CTA</div>
              </div>
            </div>
          </div>
          <div className="tl-controls" style={{display: 'flex', gap: '6px', justifyContent: 'center', padding: '6px', borderTop: '0.5px solid #30363d'}}>
            <div className="tlc" style={{width: '22px', height: '22px', borderRadius: '50%', background: '#21262d', border: '0.5px solid #30363d', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '10px', cursor: 'pointer', color: '#c9d1d9'}}>⏮</div>
            <div className="tlc" style={{width: '22px', height: '22px', borderRadius: '50%', background: '#7c3aed', border: '0.5px solid #7c3aed', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '10px', cursor: 'pointer', color: '#fff'}}>▶</div>
            <div className="tlc" style={{width: '22px', height: '22px', borderRadius: '50%', background: '#21262d', border: '0.5px solid #30363d', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '10px', cursor: 'pointer', color: '#c9d1d9'}}>⏭</div>
            <button className="export-btn-v" style={{padding: '4px 10px', background: '#3fb950', border: 'none', borderRadius: '5px', color: '#fff', fontSize: '9px', cursor: 'pointer', marginLeft: '10px'}}>Export</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// SOCIAL WORKSPACE
function SocialWorkspace({ taskMessage }) {
  const [selectedPlatforms, setSelectedPlatforms] = useState(['Instagram']);
  const platforms = ['Instagram', 'Facebook', 'Twitter', 'LinkedIn'];
  
  const togglePlatform = (p) => {
    setSelectedPlatforms(prev => 
      prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]
    );
  };
  
  return (
    <div className="panels">
      <div className="panel" style={{flex: 1}}>
        <div className="panel-header"><span className="ph-icon">📱</span><span className="ph-title">Post Preview</span></div>
        <div className="panel-body">
          <div className="ig-post" style={{background: '#fff', borderRadius: '8px', border: '0.5px solid #dbdbdb', overflow: 'hidden', margin: '8px 10px'}}>
            <div className="ig-head" style={{display: 'flex', alignItems: 'center', gap: '7px', padding: '7px 9px', borderBottom: '0.5px solid #f0f0f0'}}>
              <div className="ig-av" style={{width: '24px', height: '24px', borderRadius: '50%', background: '#e1306c', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '9px', color: '#fff', fontWeight: 500}}>YO</div>
              <div className="ig-name" style={{fontSize: '10px', color: '#262626', fontWeight: 500}}>your_brand</div>
            </div>
            <div className="ig-img" style={{background: '#1a1a3e', height: '100px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: '4px'}}>
              <span style={{fontSize: '32px'}}>🚀</span>
              <span style={{fontSize: '10px', color: '#fff'}}>Launch Day!</span>
            </div>
            <div className="ig-caption" style={{padding: '7px 9px', fontSize: '9px', color: '#262626', lineHeight: 1.5}}>
              🎉 We're officially live! Check out our new product...
              <span style={{color: '#00376b'}}>#launch #startup #newproduct</span>
            </div>
          </div>
          <div className="c-section" style={{padding: '6px 12px 3px', fontSize: '9px', color: '#484f58', textTransform: 'uppercase'}}>Platforms</div>
          <div className="plat-row" style={{display: 'flex', gap: '5px', flexWrap: 'wrap', padding: '8px 12px'}}>
            {platforms.map(p => (
              <div key={p} className={`plat ${selectedPlatforms.includes(p) ? 'on' : ''}`} 
                onClick={() => togglePlatform(p)}
                style={{padding: '4px 9px', borderRadius: '5px', fontSize: '9px', border: '0.5px solid', cursor: 'pointer', borderColor: selectedPlatforms.includes(p) ? '#7c3aed' : '#30363d', background: selectedPlatforms.includes(p) ? '#7c3aed22' : 'transparent', color: selectedPlatforms.includes(p) ? '#d2a8ff' : '#8b949e'}}>
                {p}
              </div>
            ))}
          </div>
          <div className="sched-time" style={{margin: '0 12px 8px', background: '#21262d', border: '0.5px solid #30363d', borderRadius: '6px', padding: '5px 8px', fontSize: '9px', color: '#c9d1d9'}}>
            📅 Schedule: Now (immediately)
          </div>
          <button className="post-btn" style={{margin: '0 12px 10px', padding: '7px', background: '#e1306c', border: 'none', borderRadius: '7px', color: '#fff', fontSize: '10px', cursor: 'pointer', display: 'block', width: 'calc(100% - 24px)'}}>Post to {selectedPlatforms.length} platform{selectedPlatforms.length > 1 ? 's' : ''}</button>
        </div>
      </div>
    </div>
  );
}

// FLIGHT WORKSPACE
function FlightWorkspace({ taskMessage }) {
  const [selectedSeat, setSelectedSeat] = useState('12A');
  const flights = [
    { airline: 'IndiGo', time: '06:15 → 08:30', dur: '2h 15m', price: '₹3,499', best: true },
    { airline: 'Air India', time: '09:00 → 11:20', dur: '2h 20m', price: '₹4,199', best: false },
    { airline: 'SpiceJet', time: '14:30 → 16:50', dur: '2h 20m', price: '₹2,999', best: false }
  ];
  const rows = [10, 11, 12, 13];
  const cols = ['A', 'B', 'C', 'D', 'E', 'F'];
  const takenSeats = ['10B', '10C', '11A', '11E', '12D', '13B', '13C'];
  
  return (
    <div className="panels">
      <div className="panel" style={{flex: 1}}>
        <div className="panel-header"><span className="ph-icon">✈️</span><span className="ph-title">Flights — Goa Friday</span></div>
        <div className="panel-body">
          {flights.map((f, i) => (
            <div key={i} className={`flight-card ${f.best ? 'best' : ''}`} style={{margin: '6px 12px', background: '#0d1117', border: '0.5px solid', borderColor: f.best ? '#3fb950' : '#30363d', borderRadius: '8px', padding: '9px', cursor: 'pointer'}}>
              <div className="fl-row" style={{display: 'flex', alignItems: 'center', gap: '8px'}}>
                <div className="fl-airline" style={{fontSize: '10px', color: '#e6edf3', fontWeight: 500, minWidth: '72px'}}>{f.airline}</div>
                <div className="fl-times" style={{fontSize: '10px', color: '#c9d1d9'}}>{f.time}</div>
                <div className="fl-dur" style={{fontSize: '9px', color: '#8b949e', flex: 1}}>{f.dur}</div>
                <div className="fl-price" style={{fontSize: '12px', color: '#e6edf3', fontWeight: 500}}>{f.price}</div>
              </div>
              {f.best && <div style={{fontSize: '8px', marginTop: '4px', color: '#3fb950'}}>✓ Best price</div>}
            </div>
          ))}
        </div>
      </div>
      <div className="panel" style={{flex: 1}}>
        <div className="panel-header"><span className="ph-icon">💺</span><span className="ph-title">Select Seat</span></div>
        <div className="panel-body">
          <div className="seat-map" style={{padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: '3px'}}>
            {rows.map(row => (
              <div key={row} className="seat-row" style={{display: 'flex', gap: '3px', alignItems: 'center'}}>
                <span className="seat-rn" style={{fontSize: '8px', color: '#484f58', minWidth: '16px'}}>{row}</span>
                {cols.slice(0, 3).map(col => {
                  const seatId = `${row}${col}`;
                  const taken = takenSeats.includes(seatId);
                  const selected = selectedSeat === seatId;
                  return (
                    <div key={seatId} 
                      className={`seat ${taken ? 'taken' : 'free'} ${selected ? 'sel' : ''}`}
                      onClick={() => !taken && setSelectedSeat(seatId)}
                      style={{width: '16px', height: '16px', borderRadius: '3px', border: '0.5px solid', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '7px', cursor: taken ? 'not-allowed' : 'pointer', background: selected ? '#7c3aed' : taken ? '#21262d' : 'transparent', borderColor: selected ? '#7c3aed' : '#30363d', color: selected ? '#fff' : taken ? '#484f58' : '#8b949e'}}>
                      {col}
                    </div>
                  );
                })}
                <div className="seat-gap" style={{width: '12px'}}></div>
                {cols.slice(3).map(col => {
                  const seatId = `${row}${col}`;
                  const taken = takenSeats.includes(seatId);
                  const selected = selectedSeat === seatId;
                  return (
                    <div key={seatId} 
                      className={`seat ${taken ? 'taken' : 'free'} ${selected ? 'sel' : ''}`}
                      onClick={() => !taken && setSelectedSeat(seatId)}
                      style={{width: '16px', height: '16px', borderRadius: '3px', border: '0.5px solid', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '7px', cursor: taken ? 'not-allowed' : 'pointer', background: selected ? '#7c3aed' : taken ? '#21262d' : 'transparent', borderColor: selected ? '#7c3aed' : '#30363d', color: selected ? '#fff' : taken ? '#484f58' : '#8b949e'}}>
                      {col}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
          <div style={{padding: '8px 12px', fontSize: '9px', color: '#8b949e'}}>
            Selected: <span style={{color: '#d2a8ff'}}>{selectedSeat}</span> (Window)
          </div>
          <button style={{margin: '0 12px 10px', padding: '7px', background: '#3fb950', border: 'none', borderRadius: '7px', color: '#fff', fontSize: '10px', cursor: 'pointer', display: 'block', width: 'calc(100% - 24px)'}}>Book Flight — ₹3,499</button>
        </div>
      </div>
    </div>
  );
}

// EMAIL WORKSPACE
function EmailWorkspace({ taskMessage }) {
  return (
    <div className="panels">
      <div className="panel" style={{flex: 1}}>
        <div className="panel-header"><span className="ph-icon">📧</span><span className="ph-title">Compose Email</span></div>
        <div className="panel-body" style={{padding: '12px'}}>
          <div style={{marginBottom: '8px'}}>
            <label style={{fontSize: '9px', color: '#8b949e', display: 'block', marginBottom: '4px'}}>To:</label>
            <input type="text" placeholder="recipient@email.com" style={{width: '100%', background: '#21262d', border: '0.5px solid #30363d', borderRadius: '4px', padding: '6px 8px', fontSize: '10px', color: '#e6edf3', outline: 'none'}} />
          </div>
          <div style={{marginBottom: '8px'}}>
            <label style={{fontSize: '9px', color: '#8b949e', display: 'block', marginBottom: '4px'}}>Subject:</label>
            <input type="text" placeholder="Email subject" style={{width: '100%', background: '#21262d', border: '0.5px solid #30363d', borderRadius: '4px', padding: '6px 8px', fontSize: '10px', color: '#e6edf3', outline: 'none'}} />
          </div>
          <div style={{marginBottom: '8px'}}>
            <label style={{fontSize: '9px', color: '#8b949e', display: 'block', marginBottom: '4px'}}>Message:</label>
            <textarea placeholder="Write your email..." rows={6} style={{width: '100%', background: '#21262d', border: '0.5px solid #30363d', borderRadius: '4px', padding: '6px 8px', fontSize: '10px', color: '#e6edf3', outline: 'none', resize: 'none'}} />
          </div>
          <button style={{width: '100%', padding: '7px', background: '#7c3aed', border: 'none', borderRadius: '7px', color: '#fff', fontSize: '10px', cursor: 'pointer'}}>Send Email</button>
        </div>
      </div>
    </div>
  );
}

// EXAMPLE TASKS
const EXAMPLE_TASKS = [
  { text: 'build a banking app', type: 'code' },
  { text: 'schedule a meeting tomorrow', type: 'meeting' },
  { text: 'buy 0.1 BTC now', type: 'trade' },
  { text: 'book me a shirt for weekend', type: 'shopping' },
  { text: 'fly me to Goa Friday', type: 'flight' },
  { text: 'edit my product video', type: 'video' },
  { text: 'post launch on instagram', type: 'social' },
  { text: 'renew my car insurance', type: 'browser' }
];

export default function TaskAdaptiveWorkspace({ 
  messages, input, setInput, send, loading, AgentSteps, UIComponentRenderer, sessionId, userId,
  // New props for Settings, Integrations, TaskPanel
  showSettings, setShowSettings,
  showIntegrations, setShowIntegrations,
  showTaskPanel, setShowTaskPanel,
  SettingsPanel, IntegrationsPanel, TaskPanelComponent
}) {
  const endRef = useRef(null);
  const [workspaceState, setWorkspaceState] = useState('home'); // home, thinking, active
  const [taskType, setTaskType] = useState(null);
  const [taskMessage, setTaskMessage] = useState('');
  const [thinkingSteps, setThinkingSteps] = useState([]);
  
  const codeArtifacts = extractCodeArtifacts(messages);
  
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Detect task type from latest user message.
  // Important: open the workspace reliably even after loading finishes.
  useEffect(() => {
    const lastUserMsg = messages.slice().reverse().find(m => m.role === 'user');

    if (!lastUserMsg) {
      if (!loading && messages.length === 0) {
        setWorkspaceState('home');
        setTaskType(null);
        setTaskMessage('');
      }
      return;
    }

    const detected = detectTaskType(lastUserMsg.text);
    setTaskType(detected);
    setTaskMessage(lastUserMsg.text);

    if (loading) {
      setWorkspaceState('thinking');

      // Simulate thinking steps
      setThinkingSteps([]);
      const steps = ['Understanding request...', 'Detecting task type...', 'Assembling workspace...'];
      steps.forEach((step, i) => {
        setTimeout(() => {
          setThinkingSteps(prev => [...prev, step]);
          if (i === steps.length - 1) {
            setTimeout(() => setWorkspaceState('active'), 500);
          }
        }, (i + 1) * 400);
      });
    } else {
      // If we already have messages, show the workspace even if the request finished quickly.
      if (workspaceState === 'home' || workspaceState === 'thinking') {
        setWorkspaceState('active');
      }
    }
  }, [messages, loading]);

  const hasTask = workspaceState === 'active' || (messages.some(m => m.ui_components && m.ui_components.length > 0));
  const activeTask = messages.slice().reverse().find(m => m.ui_components?.length > 0);
  const config = taskType ? TASK_CONFIG[taskType] : null;

  const handleExampleClick = (example) => {
    // Fill input but don't auto-send - let user modify and send manually
    setInput(example.text);
  };

  const renderWorkspace = () => {
    switch (taskType) {
      case 'code': return <CodeWorkspace taskMessage={taskMessage} messages={messages} artifacts={codeArtifacts} />;
      case 'meeting': return <MeetingWorkspace taskMessage={taskMessage} userId={userId} onOpenIntegrations={() => setShowIntegrations && setShowIntegrations(true)} />;
      case 'trade': return <TradeWorkspace taskMessage={taskMessage} />;
      case 'shopping': return <ShoppingWorkspace taskMessage={taskMessage} />;
      case 'flight': return <FlightWorkspace taskMessage={taskMessage} />;
      case 'video': return <VideoWorkspace taskMessage={taskMessage} />;
      case 'social': return <SocialWorkspace taskMessage={taskMessage} />;
      case 'email': return <EmailWorkspace taskMessage={taskMessage} />;
      case 'browser': return <BrowserWorkspace taskMessage={taskMessage} messages={messages} />;
      default: return <BrowserWorkspace taskMessage={taskMessage} messages={messages} />;
    }
  };

  return (
    <div className="app">
      <div className="topbar">
        <div className="logo">S</div>
        <div className="brand">Super Manager</div>
        <div className="online">
          <div className="sdot"></div>
          <span id="onlineLabel">{workspaceState === 'active' ? `Working: ${taskMessage?.slice(0, 30)}...` : 'Waiting for a task...'}</span>
        </div>
        {/* Toolbar buttons */}
        <div style={{display: 'flex', gap: '8px', marginLeft: 'auto'}}>
          <button 
            onClick={() => setShowTaskPanel && setShowTaskPanel(!showTaskPanel)}
            className="toolbar-btn"
            style={{background: showTaskPanel ? '#7c3aed22' : 'transparent', border: '0.5px solid #30363d', borderRadius: '6px', padding: '4px 8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', color: '#8b949e', fontSize: '10px'}}
            title="Tasks"
          >
            <ListTodo size={14} /> Tasks
          </button>
          <button 
            onClick={() => setShowIntegrations && setShowIntegrations(!showIntegrations)}
            className="toolbar-btn"
            style={{background: showIntegrations ? '#7c3aed22' : 'transparent', border: '0.5px solid #30363d', borderRadius: '6px', padding: '4px 8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', color: '#8b949e', fontSize: '10px'}}
            title="Integrations"
          >
            <Plug size={14} /> Connect
          </button>
          <button 
            onClick={() => setShowSettings && setShowSettings(!showSettings)}
            className="toolbar-btn"
            style={{background: showSettings ? '#7c3aed22' : 'transparent', border: '0.5px solid #30363d', borderRadius: '6px', padding: '4px 8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', color: '#8b949e', fontSize: '10px'}}
            title="Settings"
          >
            <Settings size={14} />
          </button>
        </div>
      </div>

      <div className="body">
        {/* CHAT — always left */}
        <div className="chat-col">
          <div className="chat-msgs" id="chatMsgs">
            <div className="ma" id="welcomeMsg">
              <div className="bub">Hey. Tell me what you need done. I'll figure out the rest.</div>
              <div className="mts">Now</div>
            </div>
            
            {messages.map((m, idx) => (
              <div key={idx} className={m.role === 'user' ? 'mu' : 'ma'}>
                <div className="bub">
                    {m.role === 'user' ? (
                       m.text
                    ) : (
                       <ReactMarkdown 
                         remarkPlugins={[remarkGfm]}
                         components={{
                           a: ({node, ...props}) => (
                             <a {...props} target="_blank" rel="noopener noreferrer" />
                           )
                         }}
                       >
                         {m.text || ''}
                       </ReactMarkdown>
                    )}
                </div>
                {m.steps && m.steps.length > 0 && AgentSteps && (
                    <div className="think-pill" style={{marginTop: '4px'}}>
                        <AgentSteps steps={m.steps} />
                    </div>
                )}
                <div className="mts">{new Date(m.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</div>
              </div>
            ))}
            
            {loading && (
              <div className="ma">
                <div className="bub da"><span></span><span></span><span></span></div>
              </div>
            )}
            
            <div ref={endRef} />
          </div>
          
          <div className="chat-input-area" style={{display: 'flex', borderTop: '0.5px solid #30363d', padding: '10px', background: '#0d1117', alignItems: 'center'}}>
            <input 
              type="text" 
              id="chatInput" 
              placeholder="what do you want done?" 
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') send() }}
              style={{flex: 1, background: '#161b22', border: '0.5px solid #30363d', color: '#c9d1d9', padding: '10px 14px', borderRadius: '8px', fontSize: '13px', outline: 'none'}}
            />
            <button 
              onClick={() => send()}
              disabled={!input.trim() || loading}
              style={{marginLeft: '8px', background: input.trim() ? '#7c3aed' : '#21262d', color: input.trim() ? '#fff' : '#484f58', border: 'none', borderRadius: '8px', padding: '10px 14px', cursor: input.trim() && !loading ? 'pointer' : 'not-allowed', transition: 'all 0.2s', fontWeight: 500}}
            >
              Send
            </button>
          </div>
          
          {/* QUICK ACTIONS - fills empty space */}
          <div className="quick-actions-bar" style={{padding: '10px 14px', borderTop: '1px solid #30363d', display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center'}}>
            <span style={{fontSize: '10px', color: '#484f58', fontWeight: '500'}}>Quick Start:</span>
            {[
              {text: '📝 Write code', task: 'Build a simple todo app with local storage'},
              {text: '📧 Draft email', task: 'Draft a professional email to my team about project update'},
              {text: '🎨 Design UI', task: 'Create a landing page design with modern UI'},
              {text: '📊 Analyze data', task: 'Analyze my CSV file and create visualizations'},
              {text: '🔍 Research', task: 'Research latest AI trends and summarize key points'}
            ].map((qa, i) => (
              <button
                key={i}
                onClick={() => {
                  // Fill input but don't auto-send - let user modify first
                  setInput(qa.task);
                }}
                disabled={loading}
                style={{
                  background: '#161b22',
                  border: '0.5px solid #30363d',
                  borderRadius: '6px',
                  padding: '6px 10px',
                  fontSize: '10px',
                  color: '#8b949e',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  transition: 'all 0.15s',
                  whiteSpace: 'nowrap'
                }}
                onMouseEnter={(e) => !loading && (e.target.style.background = '#7c3aed22', e.target.style.borderColor = '#7c3aed')}
                onMouseLeave={(e) => (e.target.style.background = '#161b22', e.target.style.borderColor = '#30363d')}
              >
                {qa.text}
              </button>
            ))}
          </div>
        </div>

        {/* WORKSPACE AREA */}
        <div className="ws-area">
          {workspaceState === 'home' && !hasTask && !loading ? (
            <div id="state-home" className="home">
              <div className="home-logo">S</div>
              <div>
                <div className="home-title">Nothing running yet.</div>
                <div className="home-sub" style={{marginTop: '5px'}}>Give me any task. A workspace will open automatically — built for exactly that task, with every panel it needs.</div>
              </div>
              <div className="task-examples">
                <div className="ex-label">Click any of these to see how the workspace assembles:</div>
                <div className="ex-row">
                  {EXAMPLE_TASKS.slice(0, 3).map((ex, i) => (
                    <div key={i} className="ex-pill" onClick={() => handleExampleClick(ex)}>{ex.text}</div>
                  ))}
                </div>
                <div className="ex-row">
                  {EXAMPLE_TASKS.slice(3, 6).map((ex, i) => (
                    <div key={i} className="ex-pill" onClick={() => handleExampleClick(ex)}>{ex.text}</div>
                  ))}
                </div>
                <div className="ex-row">
                  {EXAMPLE_TASKS.slice(6).map((ex, i) => (
                    <div key={i} className="ex-pill" onClick={() => handleExampleClick(ex)}>{ex.text}</div>
                  ))}
                </div>
              </div>
            </div>
          ) : workspaceState === 'thinking' || (loading && !hasTask) ? (
             <div id="state-thinking" style={{flex: '1', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '12px', padding: '24px'}}>
                <div style={{display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 14px', background: '#161b22', border: '0.5px solid #30363d', borderRadius: '10px', width: '100%', maxWidth: '420px'}}>
                  <div style={{width: '22px', height: '22px', borderRadius: '6px', background: '#7c3aed', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '10px', color: '#fff'}}>S</div>
                  <div style={{fontSize: '12px', color: '#e6edf3', fontWeight: '500'}}>Processing: {taskType ? TASK_CONFIG[taskType]?.label : 'Task'}...</div>
                </div>
                <div style={{width: '100%', maxWidth: '420px', display: 'flex', flexDirection: 'column', gap: '6px'}}>
                  {thinkingSteps.map((step, i) => (
                    <div key={i} style={{display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 10px', background: '#161b22', border: '0.5px solid #30363d', borderRadius: '6px', fontSize: '11px', color: '#8b949e'}}>
                      <span style={{color: '#3fb950'}}>✓</span> {step}
                    </div>
                  ))}
                </div>
                <div style={{width: '100%', maxWidth: '420px'}}>
                  <div style={{fontSize: '9px', color: '#484f58', marginBottom: '6px'}}>Assembling workspace panels:</div>
                  <div style={{display: 'flex', gap: '5px', flexWrap: 'wrap'}}>
                    {config?.badges?.map((b, i) => (
                      <span key={i} className={`badge ${b.cls}`}>{b.text}</span>
                    ))}
                  </div>
                </div>
             </div>
          ) : workspaceState === 'active' || hasTask ? (
            <div id="state-active" style={{flex: '1', display: 'flex', flexDirection: 'column', overflow: 'hidden', height: '100%', background: '#0d1117'}}>
               <div className="ws-header">
                  <span style={{fontSize: '12px'}}>{config?.icon || '⚡'}</span>
                  <span className="wsh-label">{taskMessage || 'Active Task'}</span>
                  {config?.badges?.map((b, i) => (
                    <span key={i} className={`badge ${b.cls}`}>{b.text}</span>
                  ))}
                  <div className="live-ind"><div className="ldot"></div>live</div>
               </div>
               {activeTask && activeTask.ui_components && activeTask.ui_components.length > 0 ? (
                 <div className="panels" style={{flex: 1, display: 'flex', overflow: 'hidden'}}>
                    <div style={{flex: 1, overflowY: 'auto', padding: '20px'}}>
                      {UIComponentRenderer && <UIComponentRenderer components={activeTask.ui_components} sessionId={sessionId} />}
                    </div>
                 </div>
               ) : (
                 renderWorkspace()
               )}
            </div>
          ) : (
            <div style={{flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#8b949e'}}>
              Task Completed or Cancelled.
            </div>
          )}
        </div>
        
        {/* Task Panel (Right sidebar) */}
        {showTaskPanel && TaskPanelComponent && (
          <div className="task-panel" style={{width: '220px', borderLeft: '0.5px solid #30363d', background: '#0d1117', display: 'flex', flexDirection: 'column'}}>
            <div style={{padding: '10px 12px', borderBottom: '0.5px solid #30363d', display: 'flex', alignItems: 'center', justifyContent: 'space-between'}}>
              <span style={{fontSize: '11px', color: '#c9d1d9', fontWeight: 500}}>Active Tasks</span>
              <button onClick={() => setShowTaskPanel(false)} style={{background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer', padding: '2px'}}><X size={14} /></button>
            </div>
            <div style={{flex: 1, overflow: 'auto'}}>
              <TaskPanelComponent />
            </div>
          </div>
        )}
      </div>
      
      {/* Settings Modal */}
      {showSettings && SettingsPanel && (
        <div className="modal-overlay" style={{position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000}}>
          <div style={{background: '#161b22', borderRadius: '12px', border: '0.5px solid #30363d', width: '90%', maxWidth: '600px', maxHeight: '80vh', overflow: 'auto'}}>
            <div style={{padding: '16px', borderBottom: '0.5px solid #30363d', display: 'flex', alignItems: 'center', justifyContent: 'space-between'}}>
              <span style={{fontSize: '14px', color: '#e6edf3', fontWeight: 600}}>Settings</span>
              <button onClick={() => setShowSettings(false)} style={{background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer'}}><X size={18} /></button>
            </div>
            <div style={{padding: '16px'}}>
              <SettingsPanel onClose={() => setShowSettings(false)} />
            </div>
          </div>
        </div>
      )}
      
      {/* Integrations Modal */}
      {showIntegrations && IntegrationsPanel && (
        <div className="modal-overlay" style={{position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '20px'}}>
          <div style={{background: '#161b22', borderRadius: '12px', border: '0.5px solid #30363d', width: '90%', maxWidth: '800px', maxHeight: '85vh', display: 'flex', flexDirection: 'column'}}>
            <div style={{padding: '16px', borderBottom: '0.5px solid #30363d', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0}}>
              <span style={{fontSize: '14px', color: '#e6edf3', fontWeight: 600}}>Connect Integrations</span>
              <button onClick={() => setShowIntegrations(false)} style={{background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer'}}><X size={18} /></button>
            </div>
            <div style={{flex: 1, overflow: 'auto', padding: '16px'}}>
              <IntegrationsPanel onClose={() => setShowIntegrations(false)} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
