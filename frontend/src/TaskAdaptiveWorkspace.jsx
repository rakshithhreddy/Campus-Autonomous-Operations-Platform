import React, { useEffect, useRef, useState } from "react";
import "./TaskWorkspace.css";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Settings, Plug, ListTodo, Shield, X, Mail } from 'lucide-react';
import { getDevAuthHeaders } from './lib/authHeaders';

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
  browser: { icon: '🧠', label: 'Agent Swarm', badges: [{ cls: 'bp', text: 'God Mode' }, { cls: 'ba', text: 'Live' }] }
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
        const res = await fetch(`/api/integrations/`, { headers: getDevAuthHeaders() });
        if (res.ok) {
          let data = {};
          try { data = await res.json(); } catch (_) { /* empty/invalid JSON */ }
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
        title: 'Meeting',
        participants: participants.join(','),
        when,
        meeting_type,
      });
      const res = await fetch(`/api/automation/quick/meeting?${params.toString()}`, { method: 'POST', headers: getDevAuthHeaders() });
      let data = {};
      try { data = await res.json(); } catch (_) { data = { error: `Server error (${res.status})` }; }
      if (data?.status === 'integration_required') {
        setError(`Integration required: ${data?.required_integration || meeting_type}. Please connect it to continue.`);
        if (typeof onOpenIntegrations === 'function') onOpenIntegrations();
        return;
      }
      // Show meeting link whenever available, even if invitations failed (partial success)
      if (data?.meeting_url) {
        setMeetingLink(data.meeting_url);
      } else if (!res.ok || data?.status === 'failed') {
        setError(data?.error || data?.message || data?.detail || 'Failed to create meeting');
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

// EXTREME SWARM EXECUTION TERMINAL (Replaces Browser Fallback)
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
    .slice(-15);

  const tokenCount = Math.floor(Math.random() * 2000) + 500 + (steps.length * 150);
  const latency = (Math.random() * 0.4 + 0.1).toFixed(2);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '16px', gap: '16px' }}>
      <style>{`
        @keyframes flowLine {
          to { stroke-dashoffset: -20; }
        }
        @keyframes pulseNode {
          0% { box-shadow: 0 0 0 0 rgba(99, 102, 241, 0.4); }
          70% { box-shadow: 0 0 0 10px rgba(99, 102, 241, 0); }
          100% { box-shadow: 0 0 0 0 rgba(99, 102, 241, 0); }
        }
        .flowing-line {
          animation: flowLine 1s linear infinite;
        }
        .swarm-node {
          position: absolute;
          transform: translate(-50%, -50%);
          background: rgba(17, 24, 39, 0.95);
          border: 1px solid #6366f1;
          padding: 10px 14px;
          border-radius: 8px;
          color: #f8fafc;
          font-size: 11px;
          font-weight: 600;
          letter-spacing: 0.5px;
          display: flex;
          align-items: center;
          gap: 8px;
          backdrop-filter: blur(8px);
          z-index: 10;
          box-shadow: 0 4px 15px rgba(0,0,0,0.4);
        }
        .node-pulse {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #6366f1;
          animation: pulseNode 2s infinite;
        }
        .extreme-terminal::-webkit-scrollbar { width: 4px; }
        .extreme-terminal::-webkit-scrollbar-thumb { background: rgba(99, 102, 241, 0.5); border-radius: 4px; }
      `}</style>

      {/* God Mode Dashboard */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#0f111a', border: '1px solid rgba(99,102,241,0.3)', borderRadius: '12px', overflow: 'hidden', boxShadow: '0 10px 40px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.05)', animation: 'slideInRightWs 0.5s forwards' }}>
        
        {/* Top Metrics Bar */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', background: 'linear-gradient(90deg, rgba(99,102,241,0.15), rgba(15,17,26,0.95))', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{ width: '8px', height: '8px', background: '#34d399', borderRadius: '50%', boxShadow: '0 0 12px #34d399', animation: 'pulse 1.5s infinite' }} />
            <h2 style={{ margin: 0, fontSize: '14px', color: '#f8fafc', fontWeight: 700, letterSpacing: '1px', textTransform: 'uppercase' }}>Swarm Intelligence Engine</h2>
          </div>
          <div style={{ display: 'flex', gap: '20px', fontFamily: 'monospace', fontSize: '11px', fontWeight: 500 }}>
             <span style={{ color: '#818cf8' }}>MODEL_ROUTER: KIMI_PRIMARY</span>
             <span style={{ color: '#34d399' }}>LIVE_TOKENS: {tokenCount}</span>
             <span style={{ color: '#f472b6' }}>LATENCY: {latency}s</span>
          </div>
        </div>

        {/* Live Swarm Map */}
        <div style={{ height: '280px', position: 'relative', background: 'radial-gradient(circle at center, #111526 0%, #05070a 100%)', borderBottom: '1px solid rgba(99,102,241,0.2)' }}>
           {/* Grid Background */}
           <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundImage: 'linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px)', backgroundSize: '20px 20px' }} />

           {/* SVG Lines */}
           <svg width="100%" height="100%" style={{ position: 'absolute', top: 0, left: 0 }}>
             <line x1="20%" y1="50%" x2="45%" y2="25%" stroke="#6366f1" strokeWidth="2" strokeDasharray="5,5" className="flowing-line" />
             <line x1="20%" y1="50%" x2="45%" y2="75%" stroke="#6366f1" strokeWidth="2" strokeDasharray="5,5" className="flowing-line" />
             <line x1="45%" y1="25%" x2="75%" y2="50%" stroke="#34d399" strokeWidth="2" strokeDasharray="5,5" className="flowing-line" />
             <line x1="45%" y1="75%" x2="75%" y2="50%" stroke="#f472b6" strokeWidth="2" strokeDasharray="5,5" className="flowing-line" />
           </svg>

           {/* Nodes */}
           <div className="swarm-node" style={{ left: '20%', top: '50%', boxShadow: '0 0 20px rgba(99,102,241,0.3)' }}>
             <div className="node-pulse"></div> MASTER ORCHESTRATOR
           </div>
           
           <div className="swarm-node" style={{ left: '45%', top: '25%', borderColor: '#6366f1' }}>
             <div className="node-pulse" style={{ background: '#6366f1', animationDelay: '0.2s' }}></div> DOM ANALYZER
           </div>
           <div className="swarm-node" style={{ left: '45%', top: '75%', borderColor: '#f472b6' }}>
             <div className="node-pulse" style={{ background: '#f472b6', animationDelay: '0.4s' }}></div> SECURITY SANDBOX
           </div>
           
           <div className="swarm-node" style={{ left: '75%', top: '50%', borderColor: '#34d399', boxShadow: '0 0 20px rgba(52,211,153,0.2)' }}>
             <div className="node-pulse" style={{ background: '#34d399', animationDelay: '0.6s' }}></div> EXECUTION ENGINE
           </div>
        </div>

        {/* Matrix Terminal Logs */}
        <div className="extreme-terminal" style={{ flex: 1, padding: '24px', background: 'rgba(0,0,0,0.85)', overflowY: 'auto', fontFamily: 'monospace', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ color: '#a78bfa', fontSize: '11px', marginBottom: '8px', opacity: 0.9 }}>// INITIATING MULTI-AGENT SWARM FOR TARGET GOAL:</div>
          <div style={{ color: '#f8fafc', fontSize: '13px', marginBottom: '20px', background: 'rgba(255,255,255,0.05)', padding: '8px 12px', borderLeft: '3px solid #a78bfa' }}>{taskMessage || "Awaiting task execution..."}</div>
          
          {steps.map((s, i) => (
            <div key={i} style={{ display: 'flex', gap: '16px', fontSize: '12px', animation: 'slideUpFade 0.3s forwards' }}>
               <span style={{ color: '#64748b', minWidth: '70px' }}>[{String(i+1).padStart(2, '0')}:EXEC]</span>
               <span style={{ color: s.ok ? '#34d399' : s.err ? '#f43f5e' : '#818cf8', flex: 1, lineHeight: '1.4' }}>
                 {s.text}
               </span>
               {s.ok && <span style={{ color: '#34d399', opacity: 0.9 }}>[SUCCESS]</span>}
               {s.err && <span style={{ color: '#f43f5e', opacity: 0.9 }}>[FAILED]</span>}
            </div>
          ))}

          {(!steps || steps.length === 0) && (
            <div style={{ display: 'flex', gap: '8px', fontSize: '12px', color: '#34d399', marginTop: '16px' }}>
              <span style={{ animation: 'pulse 1s infinite' }}>█</span> <span>Awaiting real-time active execution logs from sub-agents...</span>
            </div>
          )}
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

// EMAIL WORKSPACE - Premium Redesign
function EmailWorkspace({ taskMessage, messages }) {
  const [to, setTo] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');

  // Auto-population from taskMessage and AI suggestions
  useEffect(() => {
    // 1. Initial extraction from user message
    const emails = extractEmails(taskMessage);
    if (emails.length > 0 && !to) setTo(emails[0]);

    // Simple extraction of body from common patterns
    if (taskMessage && !body) {
      const lowerMsg = taskMessage.toLowerCase();
      let extractedBody = '';
      
      const bodyMarkers = ['tell them', 'tell him', 'tell her', 'say that', 'about', 'message:', 'body:'];
      for (const marker of bodyMarkers) {
        const idx = lowerMsg.indexOf(marker);
        if (idx !== -1) {
          extractedBody = taskMessage.slice(idx + marker.length).trim();
          // Clean up leading punctuation
          extractedBody = extractedBody.replace(/^[:,\s]+/, '');
          break;
        }
      }
      
      if (extractedBody) {
        setBody(extractedBody);
        // Synthesize a subject if missing
        if (!subject) {
          const firstLine = extractedBody.split('\n')[0].slice(0, 40);
          setSubject(firstLine.length < extractedBody.length ? firstLine + '...' : firstLine);
        }
      }
    }

    // 2. Override with AI suggestions from confirmation data
    const lastAIMsg = messages.slice().reverse().find(m => m.role === 'ai' && m.status === 'confirm');
    if (lastAIMsg?.ui_components?.params) {
      const p = lastAIMsg.ui_components.params;
      if (p.to) setTo(p.to);
      if (p.subject) setSubject(p.subject);
      if (p.body) setBody(p.body);
    }
  }, [taskMessage, messages]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  const handleSend = async () => {
    if (!to || !subject || !body) {
      setError('Recipient, subject, and message are all required.');
      return;
    }
    setLoading(true);
    setError(null);
    setSuccess(false);
    try {
      const params = new URLSearchParams({ to, subject, body });
      const res = await fetch(`/api/automation/quick/email?${params.toString()}`, {
        method: 'POST',
        headers: getDevAuthHeaders()
      });
      
      // Safely parse JSON (guard against empty body)
      let data = {};
      const text = await res.text();
      if (text) {
        try { data = JSON.parse(text); } catch (_) { /* ignore parse error */ }
      }
      
      if (!res.ok) {
        const errMsg = data?.detail || data?.error || data?.message || `Server error (${res.status})`;
        throw new Error(errMsg);
      }
      
      if (data.status === 'failed') {
        // Backend returned 200 but marked failed (no credentials)
        setError(`⚠️ ${data.result || 'Email could not be sent'}. ${data.note || ''}`);
      } else if (data.simulated) {
        // Simulated — no real credentials
        setError(`ℹ️ Demo mode: email was simulated (not actually sent). To enable real sending, configure SMTP_EMAIL + SMTP_PASSWORD in .env.`);
        setSuccess(true);
        setTimeout(() => { setSuccess(false); setError(null); }, 8000);
      } else {
        setSuccess(true);
        setTo(''); setSubject(''); setBody('');
        setTimeout(() => setSuccess(false), 5000);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="panels" style={{ padding: '20px', height: '100%', display: 'flex', flexDirection: 'column', animation: 'fadeIn 0.4s ease-out' }}>
      <div className="panel" style={{ 
        flex: 1, 
        background: 'rgba(15, 17, 26, 0.65)', 
        backdropFilter: 'blur(16px)', 
        border: '1px solid rgba(124, 58, 237, 0.15)', 
        borderRadius: '16px', 
        overflow: 'hidden',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255,255,255,0.05)',
        display: 'flex',
        flexDirection: 'column'
      }}>
        {/* Premium Header */}
        <div style={{
          padding: '16px 24px',
          background: 'linear-gradient(90deg, rgba(124, 58, 237, 0.1) 0%, rgba(15, 17, 26, 0) 100%)',
          borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
          display: 'flex',
          alignItems: 'center',
          gap: '12px'
        }}>
          <div style={{
            width: '36px', height: '36px', borderRadius: '10px',
            background: 'linear-gradient(135deg, #7c3aed, #4f46e5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 4px 12px rgba(124, 58, 237, 0.3)'
          }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>
          </div>
          <div>
            <h2 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: '#f8fafc', letterSpacing: '-0.3px' }}>Secure Communications</h2>
            <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#94a3b8' }}>Enterprise-grade authenticated dispatch</p>
          </div>
        </div>

        {/* Body Form */}
        <div style={{ padding: '24px', flex: 1, display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
          
          {error && (
            <div style={{ padding: '12px 16px', background: 'rgba(239, 68, 68, 0.1)', borderLeft: '3px solid #ef4444', borderRadius: '0 8px 8px 0', color: '#fca5a5', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px', animation: 'slideInRight 0.3s' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
              {error}
            </div>
          )}
          
          {success && (
            <div style={{ padding: '12px 16px', background: 'rgba(34, 197, 94, 0.1)', borderLeft: '3px solid #22c55e', borderRadius: '0 8px 8px 0', color: '#86efac', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px', animation: 'slideInRight 0.3s' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
              Message dispatched securely and logged to audit trail.
            </div>
          )}

          <div style={{ position: 'relative' }}>
            <label style={{ position: 'absolute', top: '-8px', left: '12px', background: '#12141d', padding: '0 4px', fontSize: '11px', color: '#a78bfa', fontWeight: 500, zIndex: 1 }}>Recipient</label>
            <div style={{ display: 'flex', alignItems: 'center', background: 'rgba(15, 23, 42, 0.5)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '0 12px', transition: 'border-color 0.2s' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
              <input type="text" value={to} onChange={e => setTo(e.target.value)} placeholder="executive@domain.com" style={{ width: '100%', background: 'transparent', border: 'none', padding: '14px 8px', fontSize: '13px', color: '#f1f5f9', outline: 'none' }} />
            </div>
          </div>

          <div style={{ position: 'relative' }}>
            <label style={{ position: 'absolute', top: '-8px', left: '12px', background: '#12141d', padding: '0 4px', fontSize: '11px', color: '#a78bfa', fontWeight: 500, zIndex: 1 }}>Subject Line</label>
            <div style={{ display: 'flex', alignItems: 'center', background: 'rgba(15, 23, 42, 0.5)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '0 12px', transition: 'border-color 0.2s' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2"><line x1="4" y1="9" x2="20" y2="9"></line><line x1="4" y1="15" x2="20" y2="15"></line><line x1="10" y1="3" x2="8" y2="21"></line><line x1="16" y1="3" x2="14" y2="21"></line></svg>
              <input type="text" value={subject} onChange={e => setSubject(e.target.value)} placeholder="Quarterly Review Update" style={{ width: '100%', background: 'transparent', border: 'none', padding: '14px 8px', fontSize: '13px', color: '#f1f5f9', outline: 'none' }} />
            </div>
          </div>

          <div style={{ position: 'relative', flex: 1, display: 'flex', flexDirection: 'column' }}>
            <label style={{ position: 'absolute', top: '-8px', left: '12px', background: '#12141d', padding: '0 4px', fontSize: '11px', color: '#a78bfa', fontWeight: 500, zIndex: 1 }}>Message Content</label>
            <textarea value={body} onChange={e => setBody(e.target.value)} placeholder="Draft your message..." style={{ flex: 1, width: '100%', minHeight: '160px', background: 'rgba(15, 23, 42, 0.5)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '16px', fontSize: '13px', color: '#f1f5f9', outline: 'none', resize: 'none', lineHeight: '1.6', fontFamily: 'inherit' }} />
          </div>

          <div style={{ marginTop: 'auto', paddingTop: '16px', display: 'flex', justifyContent: 'flex-end', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            <button 
              onClick={handleSend} 
              disabled={loading} 
              style={{
                padding: '12px 24px', 
                background: loading ? 'rgba(124, 58, 237, 0.5)' : 'linear-gradient(135deg, #7c3aed, #4f46e5)', 
                border: 'none', 
                borderRadius: '8px', 
                color: '#fff', 
                fontSize: '13px', 
                fontWeight: 600, 
                cursor: loading ? 'not-allowed' : 'pointer', 
                display: 'flex', 
                alignItems: 'center', 
                gap: '8px',
                boxShadow: loading ? 'none' : '0 4px 12px rgba(124, 58, 237, 0.3)',
                transition: 'all 0.2s',
                opacity: loading ? 0.7 : 1
              }}
            >
              {loading ? (
                <><div className="spin-loader" style={{ width: '14px', height: '14px', border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></div> Authenticating...</>
              ) : (
                <><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg> Dispatch Securely</>
              )}
            </button>
          </div>
          
        </div>
      </div>
      <style>{`
        @keyframes slideInRight { from { opacity: 0; transform: translateX(-10px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}

// VERIFIED WORKING TASKS — tested and confirmed end-to-end
const CAPABILITY_GROUPS = [
  {
    category: 'code',
    icon: '⚡',
    label: 'Code & Build',
    color: '#818cf8',
    tasks: [
      { text: 'build a beautiful todo app in HTML CSS JS', send: true },
      { text: 'write a Python web scraper for product prices', send: true },
      { text: 'create a React dashboard with charts', send: true },
      { text: 'build a REST API in FastAPI with auth', send: true },
    ]
  },
  {
    category: 'browser',
    icon: '🌐',
    label: 'Research & Web',
    color: '#34d399',
    tasks: [
      { text: 'what is Bitcoin price right now', send: true },
      { text: 'research the best AI tools in 2025', send: true },
      { text: 'find top 5 laptops under $1000 with specs', send: true },
      { text: 'get latest news about OpenAI', send: true },
    ]
  },
  {
    category: 'email',
    icon: '✉️',
    label: 'Email & Comms',
    color: '#f472b6',
    tasks: [
      { text: 'draft a professional project update email to my team', send: true },
      { text: 'write a cold outreach email to a potential client', send: true },
      { text: 'compose a follow-up email after a meeting', send: true },
    ]
  },
  {
    category: 'meeting',
    icon: '📅',
    label: 'Meetings',
    color: '#60a5fa',
    tasks: [
      { text: 'schedule a team standup meeting for tomorrow at 10am', send: true },
      { text: 'create a Jitsi meeting link for a client call', send: true },
    ]
  },
];

// Flat list for backward compat
const EXAMPLE_TASKS = CAPABILITY_GROUPS.flatMap(g => g.tasks.map(t => ({ text: t.text, type: g.category })));

export default function TaskAdaptiveWorkspace({ 
  messages, input, setInput, attachments = [], setAttachments, send, loading, AgentSteps, UIComponentRenderer, sessionId, userId,
  // New props for Settings, Integrations, TaskPanel
  showSettings, setShowSettings,
  showIntegrations, setShowIntegrations,
  showGovernance, setShowGovernance,
  showFacultyEmail, setShowFacultyEmail,
  showTaskPanel, setShowTaskPanel,
  SettingsPanel, IntegrationsPanel, GovernancePanel, FacultyEmailPanel, TaskPanelComponent
}) {
  const endRef = useRef(null);
  const fileInputRef = useRef(null);
  const [workspaceState, setWorkspaceState] = useState('home'); // home, thinking, active
  const [taskType, setTaskType] = useState(null);
  const [taskMessage, setTaskMessage] = useState('');
  const [thinkingSteps, setThinkingSteps] = useState([]);
  const [newOp, setNewOp] = useState(false);
  
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

      // Simulate thinking steps (dramatic boot sequence)
      setThinkingSteps([]);
      const steps = [
        'Analyzing intent...',
        'Classifying risk level...',
        'Routing to execution pipeline...',
        'Assembling workspace...',
        'Connecting sub-agents...'
      ];
      steps.forEach((step, i) => {
        setTimeout(() => {
          setThinkingSteps(prev => [...prev, step]);
          if (i === steps.length - 1) {
            setTimeout(() => setWorkspaceState('active'), 600);
          }
        }, (i + 1) * 350);
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
  const activeTaskSignature = activeTask
    ? `${activeTask.timestamp || ''}:${activeTask.text || ''}`
    : `${taskMessage || ''}:${messages.length}`;

  const taskPanelOpenedForTaskRef = useRef(false);
  const lastTaskSignatureRef = useRef('');

  useEffect(() => {
    if (lastTaskSignatureRef.current !== activeTaskSignature) {
      lastTaskSignatureRef.current = activeTaskSignature;
      taskPanelOpenedForTaskRef.current = false;
    }
  }, [activeTaskSignature]);

  const toggleTaskPanel = () => {
    setShowTaskPanel && setShowTaskPanel(!showTaskPanel);
  };

  const localSend = (...args) => {
    if (newOp) setNewOp(false);
    return send(...args);
  };

  const fileToAttachment = (file) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({
      filename: file.name,
      content_type: file.type || 'application/octet-stream',
      data: reader.result,
      size: file.size,
    });
    reader.onerror = () => reject(new Error(`Failed to read file: ${file.name}`));
    reader.readAsDataURL(file);
  });

  const addFiles = async (filesLike) => {
    if (!setAttachments) return;
    const files = Array.from(filesLike || []);
    if (!files.length) return;
    try {
      const prepared = await Promise.all(files.map(fileToAttachment));
      setAttachments((prev) => {
        const next = [...prev];
        for (const item of prepared) {
          const exists = next.some(
            (existing) => existing.filename === item.filename && existing.size === item.size && existing.data === item.data
          );
          if (!exists) next.push(item);
        }
        return next;
      });
    } catch (err) {
      console.error(err);
    }
  };

  const removeAttachment = (index) => {
    if (!setAttachments) return;
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  const sendWithAttachments = () => localSend(undefined, { attachments });

  const handleExampleClick = (example) => {
    const text = example.text || example;
    setInput(text);
    // Auto-send — these are verified working tasks
    setTimeout(() => {
      localSend(text);
    }, 80);
  };

  const renderWorkspace = () => {
    switch (taskType) {
      case 'code': return <CodeWorkspace taskMessage={taskMessage} messages={messages} artifacts={codeArtifacts} />;
      case 'meeting': return <MeetingWorkspace taskMessage={taskMessage} userId={userId} onOpenIntegrations={() => setShowIntegrations && setShowIntegrations(true)} />;
      case 'email': return <EmailWorkspace taskMessage={taskMessage} messages={messages} />;
      case 'trade': 
      case 'shopping': 
      case 'flight': 
      case 'video': 
      case 'social': 
      case 'browser': 
      default: return <BrowserWorkspace taskMessage={taskMessage} messages={messages} />;
    }
  };

  return (
    <div className="app">
      <div className="topbar">
        <div className="logo">S</div>
        <div className="brand">CAOP</div>
        <div className="online">
          <div className="sdot"></div>
          <span id="onlineLabel">{workspaceState === 'active' && !newOp ? `Working: ${taskMessage?.slice(0, 30)}...` : 'Waiting for a task...'}</span>
        </div>
        {/* Toolbar buttons */}
        <div style={{display: 'flex', gap: '8px', marginLeft: 'auto'}}>
          <button
            onClick={() => setNewOp(prev => !prev)}
            className="toolbar-btn"
            style={{background: newOp ? '#7c3aed22' : 'transparent', border: '0.5px solid #30363d', borderRadius: '6px', padding: '4px 8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', color: '#8b949e', fontSize: '10px'}}
            title="New OP"
          >
            <span style={{fontSize: 12, fontWeight: 600}}>New OP</span>
          </button>

          <button 
            onClick={toggleTaskPanel}
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
            onClick={() => setShowFacultyEmail && setShowFacultyEmail(!showFacultyEmail)}
            className="toolbar-btn"
            style={{background: showFacultyEmail ? '#7c3aed22' : 'transparent', border: '0.5px solid #30363d', borderRadius: '6px', padding: '4px 8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', color: '#8b949e', fontSize: '10px'}}
            title="Faculty Email Assistant"
          >
            <Mail size={14} /> Email
          </button>
          <button 
            onClick={() => setShowSettings && setShowSettings(!showSettings)}
            className="toolbar-btn"
            style={{background: showSettings ? '#7c3aed22' : 'transparent', border: '0.5px solid #30363d', borderRadius: '6px', padding: '4px 8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', color: '#8b949e', fontSize: '10px'}}
            title="Settings"
          >
            <Settings size={14} />
          </button>
          <button 
            onClick={() => setShowGovernance && setShowGovernance(!showGovernance)}
            className="toolbar-btn"
            style={{background: showGovernance ? '#7c3aed22' : 'transparent', border: '0.5px solid #30363d', borderRadius: '6px', padding: '4px 8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', color: '#8b949e', fontSize: '10px'}}
            title="Governance"
          >
            <Shield size={14} /> Governance
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
            
            {!newOp && messages.map((m, idx) => (
              <div key={idx} className={m.role === 'user' ? 'mu' : 'ma'}>
                <div className="bub">
                    {m.role === 'user' ? (
                      <>
                        {m.text}
                        {Array.isArray(m.attachments) && m.attachments.length > 0 && (
                          <div style={{ marginTop: '8px', display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                            {m.attachments.map((a, ai) => (
                              <span
                                key={`${a.filename || 'attachment'}-${ai}`}
                                style={{
                                  fontSize: '11px',
                                  background: 'rgba(255,255,255,0.16)',
                                  border: '1px solid rgba(255,255,255,0.22)',
                                  padding: '3px 8px',
                                  borderRadius: '999px',
                                }}
                              >
                                📎 {a.filename || 'attachment'}
                              </span>
                            ))}
                          </div>
                        )}
                      </>
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
              <div className="ma" style={{animation: 'slideUpFade 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards'}}>
                <div className="bub" style={{
                  background: 'linear-gradient(135deg, rgba(17,24,39,0.9), rgba(30,27,75,0.4))',
                  border: '1px solid rgba(99,102,241,0.3)',
                  padding: '16px 20px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                  position: 'relative',
                  overflow: 'hidden'
                }}>
                  {/* Scanning shimmer effect */}
                  <div style={{
                    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
                    background: 'linear-gradient(90deg, transparent 0%, rgba(99,102,241,0.05) 50%, transparent 100%)',
                    backgroundSize: '200% 100%',
                    animation: 'shimmerBg 2s ease-in-out infinite',
                    pointerEvents: 'none'
                  }} />
                  <div style={{display: 'flex', alignItems: 'center', gap: '10px'}}>
                    <div style={{
                      width: '28px', height: '28px', borderRadius: '50%',
                      background: 'radial-gradient(circle, #6366f1 0%, #4f46e5 60%, transparent 70%)',
                      boxShadow: '0 0 20px rgba(99,102,241,0.6)',
                      animation: 'neuralPulse 1.4s infinite'
                    }} />
                    <div>
                      <div style={{fontSize: '13px', fontWeight: 600, color: '#e2e8f0', letterSpacing: '0.5px'}}>Neural Processing</div>
                      <div style={{fontSize: '10px', color: '#818cf8', fontFamily: 'monospace', marginTop: '2px'}}>
                        {taskType ? `PIPELINE → ${(TASK_CONFIG[taskType]?.label || 'Agent').toUpperCase()}` : 'INITIALIZING SWARM...'}
                      </div>
                    </div>
                  </div>
                  <div style={{display: 'flex', gap: '6px', alignItems: 'center'}}>
                    {['Intent Analysis', 'Risk Classification', 'Execution'].map((stage, i) => (
                      <div key={i} style={{
                        padding: '3px 8px', borderRadius: '4px', fontSize: '9px', fontWeight: 600,
                        letterSpacing: '0.5px', textTransform: 'uppercase', fontFamily: 'monospace',
                        background: i === 0 ? 'rgba(52,211,153,0.15)' : 'rgba(255,255,255,0.03)',
                        color: i === 0 ? '#34d399' : '#64748b',
                        border: `1px solid ${i === 0 ? 'rgba(52,211,153,0.3)' : 'rgba(255,255,255,0.05)'}`,
                        animation: i <= 1 ? 'borderGlow 2s ease-in-out infinite' : 'none',
                        animationDelay: `${i * 0.5}s`
                      }}>{stage}</div>
                    ))}
                  </div>
                </div>
              </div>
            )}
            
            <div ref={endRef} />
          </div>
          
          <div className="chat-input-area" style={{display: 'flex', borderTop: '1px solid rgba(99,102,241,0.1)', padding: '16px 20px', background: 'rgba(11,15,25,0.8)', backdropFilter: 'blur(12px)', alignItems: 'flex-end', gap: '12px'}}>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="image/*,.txt,.md,.csv,.json,.pdf,.doc,.docx,.xlsx"
              style={{ display: 'none' }}
              onChange={async (e) => {
                await addFiles(e.target.files);
                e.target.value = '';
              }}
            />
            <textarea
              id="chatInput"
              placeholder="what do you want done?"
              value={input}
              rows={1}
              onChange={(e) => {
                setInput(e.target.value);
                // Auto-resize: reset height first, then set to scrollHeight
                e.target.style.height = 'auto';
                e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                    sendWithAttachments();
                }
              }}
              onPaste={async (e) => {
                const items = Array.from(e.clipboardData?.items || []);
                const imageFiles = items
                  .filter((item) => item.kind === 'file' && item.type.startsWith('image/'))
                  .map((item) => item.getAsFile())
                  .filter(Boolean);
                if (imageFiles.length > 0) {
                  e.preventDefault();
                  await addFiles(imageFiles);
                }
              }}
              style={{
                flex: 1, background: 'rgba(17,24,39,0.8)',
                border: '1px solid rgba(99,102,241,0.2)',
                color: '#e2e8f0', padding: '14px 18px', borderRadius: '12px',
                fontSize: '14px', outline: 'none', fontFamily: 'Inter, system-ui, sans-serif',
                transition: 'border-color 0.3s, box-shadow 0.3s',
                boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.2)',
                resize: 'none', overflow: 'hidden', lineHeight: '1.5',
                minHeight: '48px', maxHeight: '120px',
              }}
              onFocus={(e) => {
                e.target.style.borderColor = 'rgba(99,102,241,0.5)';
                e.target.style.boxShadow = '0 0 0 3px rgba(99,102,241,0.15), inset 0 2px 4px rgba(0,0,0,0.2)';
              }}
              onBlur={(e) => {
                e.target.style.borderColor = 'rgba(99,102,241,0.2)';
                e.target.style.boxShadow = 'inset 0 2px 4px rgba(0,0,0,0.2)';
              }}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={loading}
              title="Attach files"
              style={{
                background: 'rgba(30,30,50,0.7)',
                color: '#a5b4fc',
                border: '1px solid rgba(99,102,241,0.25)',
                borderRadius: '12px',
                padding: '12px 14px',
                cursor: loading ? 'not-allowed' : 'pointer',
                fontWeight: 600,
                fontSize: '13px',
              }}
            >
              📎
            </button>
            <button 
              onClick={() => sendWithAttachments()}
              disabled={(!input.trim() && attachments.length === 0) || loading}
              style={{
                background: (input.trim() || attachments.length) ? 'linear-gradient(135deg, #6366f1, #8b5cf6)' : 'rgba(30,30,50,0.5)',
                color: (input.trim() || attachments.length) ? '#fff' : '#484f58',
                border: 'none', borderRadius: '12px',
                padding: '14px 20px', cursor: (input.trim() || attachments.length) && !loading ? 'pointer' : 'not-allowed',
                transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                fontWeight: 600, fontSize: '14px',
                boxShadow: (input.trim() || attachments.length) ? '0 4px 15px rgba(99,102,241,0.4)' : 'none',
                display: 'flex', alignItems: 'center', gap: '6px'
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
              Send
            </button>
          </div>
          {attachments.length > 0 && (
            <div style={{ padding: '0 20px 12px', display: 'flex', flexWrap: 'wrap', gap: '8px', background: 'rgba(11,15,25,0.8)' }}>
              {attachments.map((a, i) => (
                <div
                  key={`${a.filename || 'attachment'}-${i}`}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '8px',
                    background: 'rgba(99,102,241,0.14)',
                    border: '1px solid rgba(99,102,241,0.35)',
                    borderRadius: '999px',
                    padding: '4px 10px',
                    fontSize: '11px',
                    color: '#c7d2fe',
                  }}
                >
                  <span>📎 {a.filename || `attachment-${i + 1}`}</span>
                  <button
                    type="button"
                    onClick={() => removeAttachment(i)}
                    style={{
                      border: 'none',
                      background: 'transparent',
                      color: '#e2e8f0',
                      cursor: 'pointer',
                      fontSize: '12px',
                      lineHeight: 1,
                    }}
                    aria-label={`Remove ${a.filename || 'attachment'}`}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
          
          {/* QUICK ACTIONS - fills empty space */}
          <div className="quick-actions-bar" style={{padding: '10px 14px', borderTop: '1px solid #30363d', display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center', background: 'rgba(99, 102, 241, 0.02)'}}>
            <span style={{fontSize: '10px', color: '#484f58', fontWeight: '500'}}>Quick Start (fills only):</span>
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
                  // Auto-focus the input field so user can edit immediately
                  setTimeout(() => {
                    const chatInput = document.getElementById('chatInput');
                    if (chatInput) {
                      chatInput.focus();
                      chatInput.select();
                      // Flash highlight
                      chatInput.style.boxShadow = '0 0 0 3px rgba(99,102,241,0.4), inset 0 2px 4px rgba(0,0,0,0.2)';
                      setTimeout(() => {
                        chatInput.style.boxShadow = 'inset 0 2px 4px rgba(0,0,0,0.2)';
                      }, 300);
                    }
                  }, 50);
                }}
                disabled={loading}
                title={`Click to fill the message box\nThen review and click Send when ready`}
                style={{
                  background: '#161b22',
                  border: '0.5px solid #30363d',
                  borderRadius: '6px',
                  padding: '6px 10px',
                  fontSize: '10px',
                  color: '#8b949e',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  transition: 'all 0.15s',
                  whiteSpace: 'nowrap',
                  position: 'relative'
                }}
                onMouseEnter={(e) => !loading && (e.target.style.background = '#7c3aed22', e.target.style.borderColor = '#7c3aed', e.target.style.color = '#a78bfa')}
                onMouseLeave={(e) => (e.target.style.background = '#161b22', e.target.style.borderColor = '#30363d', e.target.style.color = '#8b949e')}
              >
                {qa.text}
              </button>
            ))}
          </div>
        </div>

        {/* WORKSPACE AREA */}
        <div className="ws-area">
          {newOp || (workspaceState === 'home' && !hasTask && !loading) ? (
            <div id="state-home" style={{
              flex: 1, display: 'flex', flexDirection: 'column',
              padding: '32px 24px', overflowY: 'auto', gap: '24px',
              background: 'radial-gradient(circle at 20% 20%, rgba(99,102,241,0.04) 0%, transparent 50%), radial-gradient(circle at 80% 80%, rgba(52,211,153,0.03) 0%, transparent 50%)'
            }}>
              {/* Header */}
              <div style={{display: 'flex', alignItems: 'center', gap: '16px'}}>
                <div style={{
                  width: '48px', height: '48px', borderRadius: '14px', flexShrink: 0,
                  background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '22px', boxShadow: '0 8px 20px rgba(99,102,241,0.35)',
                  animation: 'slideUpFade 0.5s ease both'
                }}>S</div>
                <div>
                  <div style={{fontSize: '20px', fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.4px'}}>What do you need done?</div>
                  <div style={{fontSize: '13px', color: '#64748b', marginTop: '2px'}}>Click any task below — it runs immediately, no configuration needed.</div>
                </div>
              </div>

              {/* Capability Groups */}
              {CAPABILITY_GROUPS.map((group, gi) => (
                <div key={gi} style={{animation: `slideUpFade 0.5s ease ${gi * 0.1}s both`}}>
                  <div style={{display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px'}}>
                    <span style={{fontSize: '14px'}}>{group.icon}</span>
                    <span style={{fontSize: '12px', fontWeight: 700, color: group.color, textTransform: 'uppercase', letterSpacing: '0.08em'}}>{group.label}</span>
                    <div style={{height: '1px', flex: 1, background: `linear-gradient(90deg, ${group.color}30, transparent)`}} />
                    <span style={{fontSize: '10px', color: '#34d399', fontFamily: 'monospace', background: 'rgba(52,211,153,0.1)', padding: '2px 8px', borderRadius: '4px', border: '1px solid rgba(52,211,153,0.2)'}}>VERIFIED ✓</span>
                  </div>
                  <div style={{display: 'flex', flexWrap: 'wrap', gap: '8px'}}>
                    {group.tasks.map((task, ti) => (
                      <button
                        key={ti}
                        onClick={() => handleExampleClick(task)}
                        style={{
                          padding: '9px 14px', borderRadius: '10px', fontSize: '13px', fontWeight: 500,
                          color: '#cbd5e1', cursor: 'pointer',
                          background: 'rgba(17,24,39,0.6)',
                          border: `1px solid rgba(255,255,255,0.06)`,
                          transition: 'all 0.2s cubic-bezier(0.4,0,0.2,1)',
                          textAlign: 'left', fontFamily: 'Inter, system-ui, sans-serif',
                          backdropFilter: 'blur(4px)'
                        }}
                        onMouseEnter={e => {
                          e.currentTarget.style.background = `rgba(${group.color === '#818cf8' ? '99,102,241' : group.color === '#34d399' ? '52,211,153' : group.color === '#f472b6' ? '244,114,182' : '96,165,250'},0.12)`;
                          e.currentTarget.style.borderColor = group.color + '60';
                          e.currentTarget.style.color = '#f8fafc';
                          e.currentTarget.style.transform = 'translateY(-2px)';
                          e.currentTarget.style.boxShadow = `0 4px 16px ${group.color}20`;
                        }}
                        onMouseLeave={e => {
                          e.currentTarget.style.background = 'rgba(17,24,39,0.6)';
                          e.currentTarget.style.borderColor = 'rgba(255,255,255,0.06)';
                          e.currentTarget.style.color = '#cbd5e1';
                          e.currentTarget.style.transform = 'translateY(0)';
                          e.currentTarget.style.boxShadow = 'none';
                        }}
                      >
                        {task.text}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : workspaceState === 'thinking' || (loading && !hasTask) ? (
             <div id="state-thinking" style={{flex: '1', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '24px', padding: '40px', background: 'radial-gradient(circle at center, rgba(99,102,241,0.05) 0%, transparent 60%)'}}>
                <style>{`
                  @keyframes ringPulse {
                    0% { transform: scale(0.8); opacity: 0.8; }
                    50% { transform: scale(1.2); opacity: 0.3; }
                    100% { transform: scale(0.8); opacity: 0.8; }
                  }
                  @keyframes spinSlow { to { transform: rotate(360deg); } }
                  @keyframes fadeInStagger { from { opacity: 0; transform: translateX(-10px); } to { opacity: 1; transform: translateX(0); } }
                `}</style>
                {/* Central Orb */}
                <div style={{position: 'relative', width: '120px', height: '120px', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
                  <div style={{position: 'absolute', width: '120px', height: '120px', borderRadius: '50%', border: '1px solid rgba(99,102,241,0.2)', animation: 'ringPulse 2s ease-in-out infinite'}} />
                  <div style={{position: 'absolute', width: '90px', height: '90px', borderRadius: '50%', border: '1px solid rgba(99,102,241,0.3)', animation: 'ringPulse 2s ease-in-out infinite 0.3s'}} />
                  <div style={{position: 'absolute', width: '60px', height: '60px', borderRadius: '50%', border: '1px dashed rgba(99,102,241,0.4)', animation: 'spinSlow 8s linear infinite'}} />
                  <div style={{width: '32px', height: '32px', borderRadius: '50%', background: 'radial-gradient(circle, #818cf8, #4f46e5)', boxShadow: '0 0 30px rgba(99,102,241,0.6)', animation: 'neuralPulse 1.4s infinite'}} />
                </div>

                <div style={{textAlign: 'center'}}>
                  <div style={{fontSize: '18px', fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.5px'}}>Booting Agent Swarm</div>
                  <div style={{fontSize: '12px', color: '#818cf8', fontFamily: 'monospace', marginTop: '6px'}}>
                    {taskType ? `MODE: ${(TASK_CONFIG[taskType]?.label || 'General').toUpperCase()}` : 'INITIALIZING...'}
                  </div>
                </div>

                {/* Pipeline Steps */}
                <div style={{width: '100%', maxWidth: '380px', display: 'flex', flexDirection: 'column', gap: '8px'}}>
                  {thinkingSteps.map((step, i) => (
                    <div key={i} style={{
                      display: 'flex', alignItems: 'center', gap: '12px', padding: '10px 16px',
                      background: 'rgba(17,24,39,0.6)', border: '1px solid rgba(99,102,241,0.2)',
                      borderRadius: '10px', backdropFilter: 'blur(8px)',
                      animation: `fadeInStagger 0.4s ease-out ${i * 0.15}s both`
                    }}>
                      <div style={{width: '20px', height: '20px', borderRadius: '50%', background: 'rgba(52,211,153,0.15)', border: '1px solid rgba(52,211,153,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '10px', color: '#34d399', flexShrink: 0}}>✓</div>
                      <span style={{fontSize: '13px', color: '#e2e8f0', fontWeight: 500}}>{step}</span>
                    </div>
                  ))}
                  {thinkingSteps.length < 3 && (
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: '12px', padding: '10px 16px',
                      background: 'rgba(17,24,39,0.4)', border: '1px solid rgba(255,255,255,0.05)',
                      borderRadius: '10px'
                    }}>
                      <div style={{width: '20px', height: '20px', borderRadius: '50%', background: 'rgba(99,102,241,0.15)', border: '1px solid rgba(99,102,241,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
                        <div style={{width: '6px', height: '6px', borderRadius: '50%', background: '#6366f1', animation: 'neuralPulse 1s infinite'}} />
                      </div>
                      <span style={{fontSize: '13px', color: '#64748b', fontWeight: 500}}>Processing...</span>
                    </div>
                  )}
                </div>

                <div style={{display: 'flex', gap: '8px', flexWrap: 'wrap', justifyContent: 'center'}}>
                  {config?.badges?.map((b, i) => (
                    <span key={i} className={`badge ${b.cls}`} style={{animation: `fadeInStagger 0.3s ease-out ${(i + 3) * 0.15}s both`}}>{b.text}</span>
                  ))}
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
        
        {/* Task Modal */}
        {showTaskPanel && TaskPanelComponent && (
          <div className="modal-overlay" style={{position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000}}>
            <div style={{background: '#161b22', borderRadius: '12px', border: '0.5px solid #30363d', width: '90%', maxWidth: '600px', maxHeight: '80vh', display: 'flex', flexDirection: 'column'}}>
              <div style={{padding: '16px', borderBottom: '0.5px solid #30363d', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0}}>
                <span style={{fontSize: '14px', color: '#e6edf3', fontWeight: 600}}>Tasks Dashboard</span>
                <button
                  onClick={() => setShowTaskPanel && setShowTaskPanel(false)}
                  style={{background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer', display: 'flex', alignItems: 'center'}}
                  title="Close tasks"
                >
                  <X size={18} />
                </button>
              </div>
              <div style={{flex: 1, overflow: 'auto'}}>
                <TaskPanelComponent />
              </div>
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
              <SettingsPanel onClose={() => setShowSettings(false)} userId={userId} />
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
              <IntegrationsPanel onClose={() => setShowIntegrations(false)} userId={userId} />
            </div>
          </div>
        </div>
      )}

      {/* Governance Modal */}
      {showGovernance && GovernancePanel && (
        <div className="modal-overlay" style={{position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.72)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '20px'}}>
          <div style={{background: '#0d1117', borderRadius: '12px', border: '0.5px solid #30363d', width: '95%', maxWidth: '1100px', maxHeight: '90vh', display: 'flex', flexDirection: 'column'}}>
            <div style={{padding: '16px', borderBottom: '0.5px solid #30363d', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0}}>
              <span style={{fontSize: '14px', color: '#e6edf3', fontWeight: 600}}>Governance Hub</span>
              <button onClick={() => setShowGovernance(false)} style={{background: 'none', border: 'none', color: '#8b949e', cursor: 'pointer'}}><X size={18} /></button>
            </div>
            <div style={{flex: 1, overflow: 'auto', padding: '16px'}}>
              <GovernancePanel onClose={() => setShowGovernance(false)} userId={userId} />
            </div>
          </div>
        </div>
      )}

      {/* Faculty Email Dashboard Modal */}
      {showFacultyEmail && FacultyEmailPanel && (
        <div className="modal-overlay" style={{position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '20px'}}>
          <div style={{background: 'rgba(15,17,26,0.95)', backdropFilter: 'blur(16px)', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.08)', width: '95%', maxWidth: '1400px', maxHeight: '90vh', display: 'flex', flexDirection: 'column', overflow: 'hidden', boxShadow: '0 24px 48px rgba(0,0,0,0.4)'}}>
            <div style={{padding: '16px 20px', borderBottom: '1px solid rgba(255,255,255,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0, background: 'rgba(0,0,0,0.2)'}}>
              <span style={{fontSize: '16px', color: '#f1f5f9', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px'}}><span style={{fontSize: '18px'}}>📧</span> Faculty Email Assistant</span>
              <button onClick={() => setShowFacultyEmail(false)} style={{background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#94a3b8', cursor: 'pointer', borderRadius: '8px', padding: '6px', display: 'flex', transition: 'all 0.2s'}} onMouseOver={(e) => { e.currentTarget.style.background = 'rgba(239,68,68,0.1)'; e.currentTarget.style.color = '#ef4444'; e.currentTarget.style.borderColor = 'rgba(239,68,68,0.2)'; }} onMouseOut={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; e.currentTarget.style.color = '#94a3b8'; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)'; }}><X size={18} /></button>
            </div>
            <div style={{flex: 1, overflow: 'auto', background: 'transparent'}}>
              <FacultyEmailPanel />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
