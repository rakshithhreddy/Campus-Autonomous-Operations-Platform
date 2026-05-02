import React, { useState } from 'react';
import PipelineBuilder from '../components/PipelineBuilder';

export default function PipelineDemo() {
  const [showBuilder, setShowBuilder] = useState(true);

  const handleSave = (pipelineData) => {
    console.log('Pipeline Saved:', pipelineData);
    alert('Pipeline saved successfully!\n\n' + JSON.stringify(pipelineData, null, 2));
  };

  const handleClose = () => {
    setShowBuilder(false);
  };

  if (!showBuilder) {
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <h1>Pipeline Builder Demo</h1>
        <p>Pipeline Builder was closed.</p>
        <button 
          onClick={() => setShowBuilder(true)}
          style={{
            padding: '10px 20px',
            fontSize: '16px',
            backgroundColor: '#4CAF50',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer'
          }}
        >
          Reopen Pipeline Builder
        </button>
      </div>
    );
  }

  return (
    <div>
      <PipelineBuilder 
        onClose={handleClose}
        onSave={handleSave}
      />
    </div>
  );
}
