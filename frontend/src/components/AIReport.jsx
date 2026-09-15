import React, { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import useStore from '../store/useStore';
import { askAIReportStream, getSliceAsBase64, getMontageAsBase64 } from '../api/client';

export default function AIReport() {
  const { aiMessages, setAiMessages, currentSlice, windowCenter, windowWidth, volumeInfo } = useStore();
  const [input, setInput] = useState('');
  const [sliceMode, setSliceMode] = useState('all'); // 'current' | 'all'
  const [isLoading, setIsLoading] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [aiMessages, streamingText]);

  const fetchSliceImage = useCallback(async (view, sliceIndex) => {
    try {
      const res = await getSliceAsBase64(view, sliceIndex, windowCenter, windowWidth);
      if (res.image) return `data:image/png;base64,${res.image}`;
    } catch {}
    return null;
  }, [windowCenter, windowWidth]);

  const fetchCurrentSlices = useCallback(async () => {
    const images = await Promise.all([
      fetchSliceImage('axial', currentSlice.axial),
      fetchSliceImage('sagittal', currentSlice.sagittal),
      fetchSliceImage('coronal', currentSlice.coronal),
    ]);
    return images.filter(Boolean).map((url, i) => ({
      url,
      label: ['Axial', 'Sagittal', 'Coronal'][i],
    }));
  }, [currentSlice, fetchSliceImage]);

  const fetchAllSlices = useCallback(async () => {
    // Fetch 3 montage images (one per view), each containing ALL slices as a grid
    const views = ['axial', 'sagittal', 'coronal'];
    const results = await Promise.all(
      views.map(async (v) => {
        try {
          const res = await getMontageAsBase64(v, windowCenter, windowWidth);
          if (res.image) {
            return {
              url: `data:image/png;base64,${res.image}`,
              label: `${v.charAt(0).toUpperCase() + v.slice(1)} (${res.montage_slices} slices)`,
            };
          }
        } catch {}
        return null;
      })
    );
    return results.filter(Boolean);
  }, [windowCenter, windowWidth]);

  const handleSend = useCallback(async (customPrompt, forceAllSlices = false) => {
    const text = customPrompt || input.trim();
    if (!text) return;
    if (isLoading) return;

    const images = forceAllSlices
      ? await fetchAllSlices()
      : sliceMode === 'current'
        ? await fetchCurrentSlices()
        : await fetchAllSlices();

    const content = [];
    content.push({ type: 'text', text });
    for (const img of images) {
      content.push({ type: 'image_url', image_url: { url: img.url } });
    }

    const userMsg = { role: 'user', content };
    const newMessages = [...aiMessages, userMsg];

    setAiMessages(newMessages);
    setInput('');
    setIsLoading(true);
    setStreamingText('');

    const apiMessages = newMessages.map((m) => ({
      role: m.role,
      content: m.content,
    }));

    let collected = '';

    askAIReportStream(
      apiMessages,
      'openrouter/free',
      (chunk) => {
        collected += chunk;
        setStreamingText(collected);
      },
      () => {
        setAiMessages([...newMessages, { role: 'assistant', content: collected }]);
        setStreamingText('');
        setIsLoading(false);
      },
      (err) => {
        setStreamingText('');
        setIsLoading(false);
        setAiMessages([...newMessages, { role: 'assistant', content: `Error: ${err}` }]);
      }
    );
  }, [input, sliceMode, aiMessages, isLoading, setAiMessages, fetchCurrentSlices, fetchAllSlices]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const totalSlices = volumeInfo?.shape
    ? volumeInfo.shape[0] + volumeInfo.shape[1] + volumeInfo.shape[2]
    : 0;

  return (
    <div className="flex flex-col h-full text-xs">
      {/* Chat messages */}
      <div className="flex-1 overflow-y-auto space-y-2 p-2 min-h-0">
        {aiMessages.length === 0 && !streamingText && (
          <div className="flex flex-col items-center justify-center h-full text-center text-med-text-dim gap-2 py-8">
            <div className="w-10 h-10 rounded-full bg-med-accent/10 flex items-center justify-center text-lg">
              💬
            </div>
            <p className="font-medium text-med-text">AI Medical Assistant</p>
            <p className="text-[10px] max-w-[200px]">
              Ask questions about the loaded CT scan. Select a slice mode and send your query.
            </p>
          </div>
        )}

        {aiMessages.map((msg, i) => {
          const text = Array.isArray(msg.content)
            ? msg.content.filter(c => c.type === 'text').map(c => c.text).join(' ')
            : msg.content;
          return (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[95%] rounded-lg px-2.5 py-1.5 ${
              msg.role === 'user'
                ? 'bg-med-accent/20 text-med-text border border-med-accent/30'
                : 'bg-[#1a1a28] text-med-text border border-med-border'
            }`}>
              {Array.isArray(msg.content) && msg.content.filter(c => c.type === 'image_url').length > 0 && (
                <div className="flex gap-1 mb-1.5 flex-wrap">
                  {msg.content.filter(c => c.type === 'image_url').map((img, j) => (
                    <img key={j} src={img.image_url.url} alt="Attached" className="w-10 h-10 rounded border border-med-border object-cover" />
                  ))}
                </div>
              )}
              {msg.role === 'assistant' ? (
                <div className="ai-markdown leading-relaxed">
                  <ReactMarkdown>{text}</ReactMarkdown>
                </div>
              ) : (
                <div className="whitespace-pre-wrap leading-relaxed">{text}</div>
              )}
              {msg.role === 'assistant' && (
                <button
                  onClick={() => navigator.clipboard.writeText(text)}
                  className="mt-1.5 text-med-text-dim hover:text-med-accent transition-colors"
                  title="Copy response"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                </button>
              )}
            </div>
          </div>
          );
        })}

        {streamingText && (
          <div className="flex justify-start">
            <div className="max-w-[95%] rounded-lg px-2.5 py-1.5 bg-[#1a1a28] text-med-text border border-med-border">
              <div className="ai-markdown leading-relaxed">
                <ReactMarkdown>{streamingText}</ReactMarkdown>
              </div>
              <span className="inline-block w-1.5 h-3.5 bg-med-accent animate-pulse ml-0.5 align-middle" />
            </div>
          </div>
        )}

        {isLoading && !streamingText && (
          <div className="flex justify-start">
            <div className="rounded-lg px-3 py-2 bg-[#1a1a28] border border-med-border flex items-center gap-2">
              <div className="flex gap-0.5">
                <span className="w-1.5 h-1.5 bg-med-accent rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-med-accent rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-med-accent rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-med-text-dim text-[10px]">Thinking...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Slice mode selector */}
      <div className="px-2 py-1.5 border-t border-med-border">
        <div className="flex gap-1">
          <button
            onClick={() => setSliceMode('current')}
            disabled={isLoading}
            className={`flex-1 py-1.5 rounded text-[10px] font-medium border transition-all disabled:opacity-30 ${
              sliceMode === 'current'
                ? 'bg-med-accent/20 border-med-accent text-med-accent'
                : 'bg-[#181824] border-med-border text-med-text-dim hover:text-med-text hover:border-med-accent/40'
            }`}
          >
            📎 Current slices
          </button>
          <button
            onClick={() => setSliceMode('all')}
            disabled={isLoading}
            className={`flex-1 py-1.5 rounded text-[10px] font-medium border transition-all disabled:opacity-30 ${
              sliceMode === 'all'
                ? 'bg-med-accent/20 border-med-accent text-med-accent'
                : 'bg-[#181824] border-med-border text-med-text-dim hover:text-med-text hover:border-med-accent/40'
            }`}
          >
            🖼️ All slices
          </button>
        </div>
        <p className="text-[9px] text-med-text-dim mt-1 text-center">
          {sliceMode === 'current'
            ? '3 individual slices sent as PNG'
            : `3 montage grids (one per view) containing all ${totalSlices} slices`}
        </p>
      </div>

      {/* Input area */}
      <div className="px-2 py-1.5 border-t border-med-border">
        <div className="flex gap-1.5">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about the scan..."
            rows={1}
            className="flex-1 bg-[#181824] border border-med-border rounded px-2 py-1.5 text-med-text text-xs resize-none focus:outline-none focus:border-med-accent placeholder:text-med-text-dim/50"
          />
          <div className="flex flex-col gap-1">
            <button
              onClick={() => handleSend()}
              disabled={isLoading || !input.trim()}
              className="px-3 py-1 bg-med-accent hover:bg-med-accent-hover text-white text-[10px] font-semibold rounded transition-colors disabled:opacity-30"
            >
              {isLoading ? '...' : 'Send'}
            </button>
            <button
              onClick={() => handleSend('Generate a comprehensive radiology report for this volume. Include findings, measurements, and any abnormalities detected.', true)}
              disabled={isLoading}
              className="px-3 py-1 bg-emerald-600/80 hover:bg-emerald-600 text-white text-[10px] font-semibold rounded transition-colors disabled:opacity-30"
            >
              Report
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
