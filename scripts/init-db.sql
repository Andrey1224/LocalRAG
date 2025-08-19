-- Initialize LocalRAG database

-- Create extension for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Feedback table
CREATE TABLE IF NOT EXISTS feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    question TEXT NOT NULL,
    llm_answer TEXT NOT NULL,
    citations_used JSONB,
    rating VARCHAR(10) NOT NULL CHECK (rating IN ('up', 'down')),
    reason VARCHAR(100),
    comment TEXT,
    trace_id UUID,
    llm_model VARCHAR(100),
    lang VARCHAR(10),
    user_id VARCHAR(100),
    session_id VARCHAR(100),
    request_id VARCHAR(100),
    ip_address INET,
    user_agent TEXT,
    is_hidden BOOLEAN DEFAULT FALSE,
    resolved BOOLEAN DEFAULT FALSE,
    needs_review BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Evaluation runs table
CREATE TABLE IF NOT EXISTS evaluation_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_name VARCHAR(255),
    eval_type VARCHAR(50) NOT NULL,
    llm_model VARCHAR(100),
    reranker_model VARCHAR(100),
    total_cases INTEGER NOT NULL,
    completed_cases INTEGER DEFAULT 0,
    avg_faithfulness FLOAT,
    avg_answer_relevancy FLOAT,
    avg_context_precision FLOAT,
    avg_context_recall FLOAT,
    status VARCHAR(20) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
    error_message TEXT,
    user_id VARCHAR(100),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    config JSONB
);

-- Evaluation results table
CREATE TABLE IF NOT EXISTS evaluation_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id UUID REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    case_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    ground_truth_answer TEXT,
    ground_truth_chunks JSONB,
    llm_answer TEXT,
    citations_used JSONB,
    faithfulness FLOAT,
    answer_relevancy FLOAT,
    context_precision FLOAT,
    context_recall FLOAT,
    flags JSONB,
    errors JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Document metadata table
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_id VARCHAR(255) UNIQUE NOT NULL,
    title VARCHAR(500),
    source_path TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    file_type VARCHAR(20),
    language VARCHAR(10),
    total_chunks INTEGER DEFAULT 0,
    file_size_bytes BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Request logs table
CREATE TABLE IF NOT EXISTS request_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trace_id UUID NOT NULL,
    session_id VARCHAR(100),
    user_id VARCHAR(100),
    endpoint VARCHAR(100) NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code INTEGER,
    latency_ms INTEGER,
    request_body JSONB,
    response_body JSONB,
    error_message TEXT,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON feedback(created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_trace_id ON feedback(trace_id);
CREATE INDEX IF NOT EXISTS idx_feedback_rating ON feedback(rating);
CREATE INDEX IF NOT EXISTS idx_feedback_user_id ON feedback(user_id);

CREATE INDEX IF NOT EXISTS idx_evaluation_runs_status ON evaluation_runs(status);
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_created_at ON evaluation_runs(started_at);

CREATE INDEX IF NOT EXISTS idx_evaluation_results_run_id ON evaluation_results(run_id);

CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents(doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);

CREATE INDEX IF NOT EXISTS idx_request_logs_trace_id ON request_logs(trace_id);
CREATE INDEX IF NOT EXISTS idx_request_logs_endpoint ON request_logs(endpoint);
CREATE INDEX IF NOT EXISTS idx_request_logs_created_at ON request_logs(created_at);

-- Update trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_feedback_updated_at BEFORE UPDATE ON feedback
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
