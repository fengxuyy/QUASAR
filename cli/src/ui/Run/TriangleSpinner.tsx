import React, { useState, useEffect } from 'react';
import { Text } from 'ink';

const TriangleSpinner: React.FC = () => {
    const frames = ['△', '▴', '▲', '▴']; // Sequence provided: △, ▴, ▲, ▴, △
    const [frameIndex, setFrameIndex] = useState(0);

    useEffect(() => {
        const timer = setInterval(() => {
            setFrameIndex((prev) => (prev + 1) % frames.length);
        }, 200);

        return () => clearInterval(timer);
    }, []);

    return <Text>{frames[frameIndex]}</Text>;
};

export default TriangleSpinner;
