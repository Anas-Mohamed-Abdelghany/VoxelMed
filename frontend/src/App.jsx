import React, { useEffect, useCallback } from 'react';
import useStore from './store/useStore';
import Toolbar from './components/Toolbar';
import Sidebar from './components/Sidebar';
import MPRViewer from './components/MPRViewer';
import LandingScreen from './components/LandingScreen';

export default function App() {
  const { volumeLoaded, loading, error, setError, sidebarOpen, setSidebarOpen } = useStore();

  // Auto-open sidebar on desktop, close on mobile
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    const handle = (e) => setSidebarOpen(e.matches);
    handle(mq);
    mq.addEventListener('change', handle);
    return () => mq.removeEventListener('change', handle);
  }, [setSidebarOpen]);

  // Close sidebar when navigating to landing screen
  useEffect(() => {
    if (!volumeLoaded) setSidebarOpen(false);
  }, [volumeLoaded, setSidebarOpen]);

  return (
    <div className="w-full h-full flex flex-col bg-med-dark text-med-text">
      {error && (
        <div className="absolute top-2 left-1/2 -translate-x-1/2 z-50 bg-red-600/90 text-white px-4 py-2 rounded-lg shadow-lg flex items-center gap-3">
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="text-white/70 hover:text-white text-lg">&times;</button>
        </div>
      )}
      {loading && (
        <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-3">
            <div className="w-10 h-10 border-4 border-med-accent border-t-transparent rounded-full animate-spin" />
            <span className="text-med-text-dim text-sm">Processing...</span>
          </div>
        </div>
      )}
      {volumeLoaded ? (
        <>
          <Toolbar />
          <div className="flex flex-1 overflow-hidden relative">
            {/* Mobile backdrop scrim */}
            {sidebarOpen && (
              <div
                className="md:hidden fixed inset-0 z-30 bg-black/50"
                onClick={() => setSidebarOpen(false)}
              />
            )}
            <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
            <div className="flex-1 overflow-hidden min-w-0">
              <MPRViewer />
            </div>
          </div>
        </>
      ) : (
        <LandingScreen />
      )}
    </div>
  );
}
