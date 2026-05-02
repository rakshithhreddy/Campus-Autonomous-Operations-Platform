import React from 'react'; import ReactDOM from 'react-dom/client';
// Global fetch wrapper: normalizes network errors and adds retries
import './lib/fetchWrapper';
import App from './App'; ReactDOM.createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
