import React, { useState, useEffect } from 'react';
import { Text } from 'ink';
import { registerAnimationSubscriber } from '../animationTick.js';

const frames = ['△', '▴', '▲', '▴'];

const TriangleSpinner: React.FC = () => {
    const [frameIndex, setFrameIndex] = useState(0);

    useEffect(() => {
        const advance = () => setFrameIndex(prev => (prev + 1) % frames.length);
        return registerAnimationSubscriber(advance);
    }, []);

    return <Text>{frames[frameIndex]}</Text>;
};

export default TriangleSpinner;
