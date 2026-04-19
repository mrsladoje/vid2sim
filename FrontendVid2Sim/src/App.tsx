import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import type { Variants } from 'framer-motion';
import Navigation from './components/Navigation';
import HeroSection from './components/HeroSection';
import UploadSection from './components/UploadSection';
import ProcessingScreen from './components/ProcessingScreen';
import SimulationViewer from './components/SimulationViewer';
import FeaturesSection from './components/FeaturesSection';
import HowItWorksSection from './components/HowItWorksSection';
import FaqSection from './components/FaqSection';
import ContactSection from './components/ContactSection';
import Footer from './components/Footer';
import BackgroundFX from './components/BackgroundFX';

export type AppState =
  | 'hero'
  | 'features'
  | 'how-it-works'
  | 'faq'
  | 'contact'
  | 'upload'
  | 'processing'
  | 'simulation';

export const WORKSPACE_STATES: AppState[] = ['upload', 'processing', 'simulation'];

const PAGE_VARIANTS: Variants = {
  initial: { opacity: 0, y: 12 },
  enter: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] }
  },
  exit: {
    opacity: 0,
    y: -8,
    transition: { duration: 0.2, ease: 'easeIn' }
  }
};

function App() {
  const [appState, setAppState] = useState<AppState>('hero');
  const [jobId, setJobId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const inAppWorkspace = WORKSPACE_STATES.includes(appState);

  const renderCurrentState = () => {
    switch (appState) {
      case 'hero':
        return <HeroSection onStart={() => setAppState('upload')} />;
      case 'features':
        return <FeaturesSection onStart={() => setAppState('upload')} />;
      case 'how-it-works':
        return <HowItWorksSection onStart={() => setAppState('upload')} />;
      case 'faq':
        return <FaqSection />;
      case 'contact':
        return <ContactSection />;
      case 'upload':
        return (
          <UploadSection
            onPipelineStarted={(startedJobId, startedSessionId) => {
              setJobId(startedJobId);
              setSessionId(startedSessionId);
              setAppState('processing');
            }}
            onUploadCompleteStub={() => setAppState('processing')}
          />
        );
      case 'processing':
        return (
          <ProcessingScreen
            jobId={jobId}
            onComplete={(completedSessionId) => {
              if (completedSessionId) setSessionId(completedSessionId);
              setAppState('simulation');
            }}
          />
        );
      case 'simulation':
        return <SimulationViewer sessionId={sessionId} />;
      default:
        return <HeroSection onStart={() => setAppState('upload')} />;
    }
  };

  return (
    <div className="min-h-screen w-full flex flex-col bg-background">
      <BackgroundFX />
      <Navigation appState={appState} setAppState={setAppState} />

      <main className="flex-1 flex flex-col pt-16 md:pt-[5.25rem]">
        <AnimatePresence mode="wait">
          <motion.div
            key={appState}
            variants={PAGE_VARIANTS}
            initial="initial"
            animate="enter"
            exit="exit"
            className="flex-1 flex flex-col"
          >
            {renderCurrentState()}
          </motion.div>
        </AnimatePresence>

        {!inAppWorkspace && <Footer setAppState={setAppState} />}
      </main>
    </div>
  );
}

export default App;
