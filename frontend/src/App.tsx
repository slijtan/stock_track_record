import { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';

// Lazy load pages for better initial load performance
const ChannelList = lazy(() => import('./pages/ChannelList'));
const ChannelDetails = lazy(() => import('./pages/ChannelDetails'));
const StockDrilldown = lazy(() => import('./pages/StockDrilldown'));
const NotFound = lazy(() => import('./pages/NotFound'));

function LoadingFallback() {
  return (
    <div className="flex justify-center items-center h-64">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
    </div>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <Router>
        <Layout>
          <Suspense fallback={<LoadingFallback />}>
            <Routes>
              <Route path="/" element={<ChannelList />} />
              <Route path="/channels/:id" element={<ChannelDetails />} />
              <Route path="/channels/:id/stocks/:ticker" element={<StockDrilldown />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </Layout>
      </Router>
    </ErrorBoundary>
  );
}

export default App;
